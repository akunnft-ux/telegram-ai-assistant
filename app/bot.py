import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from app.config import TELEGRAM_BOT_TOKEN
from app.gemini import get_response, process_long_document, generate_document_content
from app.database import init_db, save_message, get_recent_messages, get_all_memories, delete_memory
from app.memory import extract_memory_from_response
from app.tools import (
    extract_text_from_file, split_text_into_chunks,
    SUPPORTED_EXTENSIONS, CHUNK_SIZE,
    create_pdf_file, create_docx_file,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo! Aku asisten AI kamu. Langsung aja ngobrol 😊")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    save_message(user_id, "user", user_message)

    recent_messages = get_recent_messages(user_id, limit=20)

    await update.message.chat.send_action("typing")

    raw_response = await get_response(user_id, user_message, recent_messages)

    clean_response = extract_memory_from_response(user_id, raw_response)

    save_message(user_id, "assistant", clean_response)

    await update.message.reply_text(clean_response)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle dokumen yang dikirim user"""
    user_id = str(update.effective_user.id)
    document = update.message.document

    if not document:
        return

    file_name = document.file_name or "unknown"
    file_size = document.file_size or 0

    if file_size > 20 * 1024 * 1024:
        await update.message.reply_text("File terlalu besar. Maksimal 20MB ya.")
        return

    _, ext = os.path.splitext(file_name)
    ext = ext.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        await update.message.reply_text(
            f"Format {ext} belum didukung.\n\nFormat yang didukung:\n{supported}"
        )
        return

    await update.message.chat.send_action("typing")

    try:
        file = await document.get_file()
        tmp_path = f"/tmp/{user_id}_{file_name}"
        await file.download_to_drive(tmp_path)

        text, error = extract_text_from_file(tmp_path)

        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        if error:
            await update.message.reply_text(error)
            return

        caption = update.message.caption or ""
        char_count = len(text)

        if char_count <= CHUNK_SIZE:
            if caption:
                user_message = f"[Dokumen: {file_name} ({char_count} karakter)]\n\nPesan: {caption}\n\nIsi dokumen:\n{text}"
            else:
                user_message = f"[Dokumen: {file_name} ({char_count} karakter)]\n\nIsi dokumen:\n{text}\n\nTolong baca dan rangkum isi dokumen ini."

            save_message(user_id, "user", user_message)
            recent_messages = get_recent_messages(user_id, limit=20)

            await update.message.chat.send_action("typing")

            raw_response = await get_response(user_id, user_message, recent_messages)
            clean_response = extract_memory_from_response(user_id, raw_response)

            save_message(user_id, "assistant", clean_response)

        else:
            chunks = split_text_into_chunks(text)
            num_chunks = len(chunks)

            await update.message.reply_text(
                f"📄 Dokumen {file_name} cukup panjang ({char_count:,} karakter, {num_chunks} bagian).\n"
                f"Sedang membaca... estimasi {num_chunks + 1} langkah."
            )

            doc_info = f"[Dokumen panjang: {file_name} ({char_count:,} karakter, {num_chunks} bagian)]"
            if caption:
                doc_info += f"\nPesan user: {caption}"
            save_message(user_id, "user", doc_info)

            recent_messages = get_recent_messages(user_id, limit=20)

            await update.message.chat.send_action("typing")

            raw_response = await process_long_document(
                user_id, chunks, file_name, caption, recent_messages
            )
            clean_response = extract_memory_from_response(user_id, raw_response)

            save_message(user_id, "assistant", clean_response)

        if len(clean_response) > 4096:
            for i in range(0, len(clean_response), 4096):
                await update.message.reply_text(clean_response[i:i + 4096])
        else:
            await update.message.reply_text(clean_response)

    except Exception as e:
        print(f"❌ Error handle document: {e}")
        await update.message.reply_text("Maaf, gagal membaca dokumen. Coba kirim ulang ya.")


# ============================================
# DOCUMENT CREATION COMMANDS
# ============================================

async def create_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, doc_type: str):
    """Handler untuk buat PDF atau DOCX"""
    user_id = str(update.effective_user.id)

    if not context.args:
        examples = (
            f"Tulis instruksi setelah /{doc_type}\n\n"
            f"Contoh:\n"
            f"/{doc_type} buatkan rangkuman tentang AI\n"
            f"/{doc_type} rangkum percakapan kita tadi\n"
            f"/{doc_type} buat laporan dari dokumen yang aku kirim"
        )
        await update.message.reply_text(examples)
        return

    instruction = " ".join(context.args)

    await update.message.chat.send_action("typing")
    await update.message.reply_text(f"📝 Sedang membuat dokumen {doc_type.upper()}...")

    recent_messages = get_recent_messages(user_id, limit=20)

    # Generate konten via Gemini
    content = await generate_document_content(user_id, instruction, recent_messages)

    if not content:
        await update.message.reply_text("Gagal membuat konten dokumen. Coba lagi ya.")
        return

    try:
        file_path = f"/tmp/{user_id}_document.{doc_type}"

        # Buat file
        if doc_type == "pdf":
            title = create_pdf_file(content, file_path)
        else:
            title = create_docx_file(content, file_path)

        # Bersihkan judul untuk nama file
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:50].strip()
        if not safe_title:
            safe_title = "dokumen"

        await update.message.chat.send_action("upload_document")

        with open(file_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"{safe_title}.{doc_type}",
                caption=f"📄 {title}"
            )

        # Simpan ke percakapan
        save_message(user_id, "user", f"/{doc_type} {instruction}")
        save_message(user_id, "assistant", f"[Dokumen {doc_type.upper()} dibuat: {title}]")

        if os.path.exists(file_path):
            os.remove(file_path)

        print(f"✅ {doc_type.upper()} created: {title}")

    except Exception as e:
        print(f"❌ Error create {doc_type}: {e}")
        await update.message.reply_text(f"Gagal membuat file {doc_type.upper()}. Coba lagi ya.")


async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await create_document_handler(update, context, "pdf")


async def docx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await create_document_handler(update, context, "docx")


# ============================================
# MEMORY COMMANDS
# ============================================

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memories = get_all_memories(user_id)

    if not memories:
        await update.message.reply_text("Aku belum punya catatan apa-apa tentang kamu.")
        return

    lines = ["Ini yang aku ingat tentang kamu:\n"]
    for key, value in memories:
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {value}")

    await update.message.reply_text("\n".join(lines))


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text("Tulis key yang mau dihapus.\nContoh: /forget nama_kucing")
        return

    key = "_".join(context.args).lower()
    deleted = delete_memory(user_id, key)

    if deleted:
        await update.message.reply_text(f"Oke, aku sudah lupa tentang '{key}'.")
    else:
        await update.message.reply_text(f"Aku tidak punya catatan '{key}'.")


async def clearmemory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    memories = get_all_memories(user_id)

    if not memories:
        await update.message.reply_text("Tidak ada memory yang perlu dihapus.")
        return

    from app.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    await update.message.reply_text(f"Done. {deleted} memory dihapus semua.")


# ============================================
# MAIN
# ============================================

def main():
    init_db()

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("clearmemory", clearmemory_command))
    app.add_handler(CommandHandler("pdf", pdf_command))
    app.add_handler(CommandHandler("docx", docx_command))

    # Document handler
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Text handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

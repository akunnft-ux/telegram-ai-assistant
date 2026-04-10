import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from app.config import TELEGRAM_BOT_TOKEN
from app.gemini import get_response, process_long_document, generate_document_content, analyze_image
from app.database import init_db, save_message, get_recent_messages, get_all_memories, delete_memory, clear_history
from app.memory import extract_memory_from_response

from app.tools import (
    extract_text_from_file, split_text_into_chunks,
    SUPPORTED_EXTENSIONS, CHUNK_SIZE,
    create_pdf_file, create_docx_file,

    # TVL
    get_tvl_growth, format_tvl_result,

    # Crypto market
    get_global_market, format_global_result,
    get_trending_coins, format_trending_result,
    get_top_movers, format_top_movers_result,
    get_fear_greed, format_fear_greed_result,
    get_coin_detail, format_coin_detail_result,
    get_full_market_data, build_daily_pick_prompt,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
IMAGE_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


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


# ============================================
# PHOTO HANDLER (kirim sebagai foto)
# ============================================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    await update.message.chat.send_action("typing")

    try:
        file = await photo.get_file()
        image_bytes = await file.download_as_bytearray()

        user_msg = "[User mengirim gambar]"
        if caption:
            user_msg += f"\nPesan: {caption}"
        save_message(user_id, "user", user_msg)

        recent_messages = get_recent_messages(user_id, limit=20)

        raw_response = await analyze_image(user_id, bytes(image_bytes), caption, recent_messages)
        clean_response = extract_memory_from_response(user_id, raw_response)
        save_message(user_id, "assistant", clean_response)

        if len(clean_response) > 4096:
            for i in range(0, len(clean_response), 4096):
                await update.message.reply_text(clean_response[i:i + 4096])
        else:
            await update.message.reply_text(clean_response)

    except Exception as e:
        print(f"❌ Error handle photo: {e}")
        await update.message.reply_text("Maaf, gagal menganalisis gambar. Coba kirim ulang ya.")


# ============================================
# DOCUMENT HANDLER (file dokumen + gambar sebagai file)
# ============================================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # --- Kalau file gambar, analisis pakai Gemini ---
    if ext in IMAGE_EXTENSIONS:
        await update.message.chat.send_action("typing")

        try:
            file = await document.get_file()
            image_bytes = await file.download_as_bytearray()
            caption = update.message.caption or ""
            mime_type = IMAGE_MIME_MAP.get(ext, "image/jpeg")

            user_msg = f"[User mengirim gambar: {file_name}]"
            if caption:
                user_msg += f"\nPesan: {caption}"
            save_message(user_id, "user", user_msg)

            recent_messages = get_recent_messages(user_id, limit=20)

            raw_response = await analyze_image(user_id, bytes(image_bytes), caption, recent_messages, mime_type)
            clean_response = extract_memory_from_response(user_id, raw_response)
            save_message(user_id, "assistant", clean_response)

            if len(clean_response) > 4096:
                for i in range(0, len(clean_response), 4096):
                    await update.message.reply_text(clean_response[i:i + 4096])
            else:
                await update.message.reply_text(clean_response)
            return

        except Exception as e:
            print(f"❌ Error handle image document: {e}")
            await update.message.reply_text("Maaf, gagal menganalisis gambar. Coba kirim ulang ya.")
            return

    # --- Kalau bukan gambar, proses sebagai dokumen teks ---
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

    content = await generate_document_content(user_id, instruction, recent_messages)

    if not content:
        await update.message.reply_text("Gagal membuat konten dokumen. Coba lagi ya.")
        return

    try:
        file_path = f"/tmp/{user_id}_document.{doc_type}"

        if doc_type == "pdf":
            title = create_pdf_file(content, file_path)
        else:
            title = create_docx_file(content, file_path)

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
# CRYPTO COMMANDS
# ============================================

async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")

    try:
        global_result = await get_global_market()
        fear_result = await get_fear_greed()

        text_parts = [
            format_global_result(global_result),
            format_fear_greed_result(fear_result),
        ]

        await update.message.reply_text("\n\n".join(text_parts))

    except Exception as e:
        print(f"❌ Error /market: {e}")
        await update.message.reply_text("Maaf, gagal mengambil data market.")


async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")

    try:
        result = await get_trending_coins()
        await update.message.reply_text(format_trending_result(result))
    except Exception as e:
        print(f"❌ Error /trending: {e}")
        await update.message.reply_text("Maaf, gagal mengambil data trending.")


async def movers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")

    try:
        result = await get_top_movers()
        await update.message.reply_text(format_top_movers_result(result))
    except Exception as e:
        print(f"❌ Error /movers: {e}")
        await update.message.reply_text("Maaf, gagal mengambil data movers.")


async def fear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")

    try:
        result = await get_fear_greed()
        await update.message.reply_text(format_fear_greed_result(result))
    except Exception as e:
        print(f"❌ Error /fear: {e}")
        await update.message.reply_text("Maaf, gagal mengambil Fear & Greed Index.")


async def tvl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Tulis nama protokol.\n\nContoh:\n"
            "/tvl aave\n"
            "/tvl lido\n"
            "/tvl uniswap"
        )
        return

    protocol_name = " ".join(context.args)
    await update.message.chat.send_action("typing")

    try:
        result = await get_tvl_growth(protocol_name)
        await update.message.reply_text(format_tvl_result(result))
    except Exception as e:
        print(f"❌ Error /tvl: {e}")
        await update.message.reply_text("Maaf, gagal mengambil data TVL.")


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text(
            "Tulis coin id dari CoinGecko.\n\nContoh:\n"
            "/analyze bitcoin\n"
            "/analyze ethereum\n"
            "/analyze solana"
        )
        return

    coin_id = context.args[0].lower()
    await update.message.chat.send_action("typing")

    try:
        result = await get_coin_detail(coin_id)

        if "error" in result:
            await update.message.reply_text(result["error"])
            return

        basic_text = format_coin_detail_result(result)
        await update.message.reply_text(basic_text)

        await update.message.chat.send_action("typing")

        prompt = (
            "You are a crypto analyst.\n"
            "Based only on the data below, write:\n"
            "1. A short analysis in 2-3 sentences\n"
            "2. A Farcaster-ready post in English, max 280 characters\n"
            "Rules: include $TICKER, mention specific data, no price prediction, end with NFA/DYOR 🔍\n\n"
            f"{basic_text}"
        )

        save_message(user_id, "user", f"/analyze {coin_id}")
        recent_messages = get_recent_messages(user_id, limit=5)

        raw_response = await get_response(user_id, prompt, recent_messages)
        clean_response = extract_memory_from_response(user_id, raw_response)
        save_message(user_id, "assistant", clean_response)

        await update.message.reply_text(f"🤖 AI Analysis:\n\n{clean_response}")

    except Exception as e:
        print(f"❌ Error /analyze: {e}")
        await update.message.reply_text("Maaf, gagal menganalisis coin.")


async def daily_pick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    await update.message.reply_text("⏳ Mengambil data market...")
    await update.message.chat.send_action("typing")

    try:
        market_data = await get_full_market_data()

        await update.message.reply_text("🤖 Menganalisa dan memilih 1 top crypto...")
        await update.message.chat.send_action("typing")

        prompt = build_daily_pick_prompt(market_data)

        save_message(user_id, "user", "/daily_pick")
        recent_messages = get_recent_messages(user_id, limit=5)

        raw_response = await get_response(user_id, prompt, recent_messages)
        clean_response = extract_memory_from_response(user_id, raw_response)
        save_message(user_id, "assistant", clean_response)

        await update.message.reply_text(f"📊 Daily Pick:\n\n{clean_response}")

    except Exception as e:
        print(f"❌ Error /daily_pick: {e}")
        await update.message.reply_text("Maaf, gagal membuat daily pick.")


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


async def clearhistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    deleted = clear_history(user_id)

    if deleted > 0:
        await update.message.reply_text(f"Done. {deleted} pesan dihapus. Percakapan dimulai dari awal, tapi aku masih ingat info tentang kamu.")
    else:
        await update.message.reply_text("Tidak ada history yang perlu dihapus.")
        
        
async def post_init(application):
    """Register commands ke Telegram biar muncul di menu"""
    from telegram import BotCommand

    commands = [
        BotCommand("start", "Mulai percakapan"),

        # Crypto
        BotCommand("daily_pick", "Pilih 1 crypto terbaik hari ini + draft cast"),
        BotCommand("market", "Global market overview + Fear & Greed"),
        BotCommand("trending", "Trending coins dari CoinGecko"),
        BotCommand("movers", "Top gainers & losers 24h"),
        BotCommand("fear", "Fear & Greed Index"),
        BotCommand("tvl", "TVL protokol - /tvl [nama]"),
        BotCommand("analyze", "Analisa coin - /analyze [coin]"),

        # Dokumen
        BotCommand("pdf", "Buat dokumen PDF - /pdf [instruksi]"),
        BotCommand("docx", "Buat dokumen DOCX - /docx [instruksi]"),

        # Memory
        BotCommand("memory", "Lihat semua memory"),
        BotCommand("forget", "Hapus 1 memory - /forget [key]"),
        BotCommand("clearmemory", "Hapus semua memory"),
        BotCommand("clearhistory", "Hapus semua percakapan"),
    ]

    await application.bot.set_my_commands(commands)
    print("✅ Bot commands registered")
        
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
        .post_init(post_init)
        .build()
    )

    # Commands
    # Commands
    app.add_handler(CommandHandler("start", start))

    # Crypto commands
    app.add_handler(CommandHandler("daily_pick", daily_pick_command))
    app.add_handler(CommandHandler("market", market_command))
    app.add_handler(CommandHandler("trending", trending_command))
    app.add_handler(CommandHandler("movers", movers_command))
    app.add_handler(CommandHandler("fear", fear_command))
    app.add_handler(CommandHandler("tvl", tvl_command))
    app.add_handler(CommandHandler("analyze", analyze_command))

    # Memory & document commands
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("clearmemory", clearmemory_command))
    app.add_handler(CommandHandler("clearhistory", clearhistory_command))
    app.add_handler(CommandHandler("pdf", pdf_command))
    app.add_handler(CommandHandler("docx", docx_command))

    # Photo handler
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Document handler
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Text handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

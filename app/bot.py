from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from app.config import TELEGRAM_BOT_TOKEN
from app.gemini import get_response
from app.database import init_db, save_message, get_recent_messages, get_all_memories, delete_memory, delete_all_memories
from app.memory import extract_memory_from_response


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo! Aku asisten AI kamu. Langsung aja ngobrol 😊")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    # Simpan pesan user ke DB
    save_message(user_id, "user", user_message)

    # Ambil recent history dari DB
    recent_messages = get_recent_messages(user_id, limit=20)

    # Typing indicator
    await update.message.chat.send_action("typing")

    # Kirim ke Gemini (1 API call)
    raw_response = await get_response(user_id, user_message, recent_messages)

    # Parse [MEMORY] block, simpan ke DB, dapat jawaban bersih
    clean_response = extract_memory_from_response(user_id, raw_response)

    # Simpan jawaban bersih ke DB
    save_message(user_id, "assistant", clean_response)

    # Kirim jawaban bersih ke user
    await update.message.reply_text(clean_response)

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
    deleted = delete_all_memories(user_id)

    if deleted > 0:
        await update.message.reply_text(f"Oke, semua memory ({deleted} catatan) sudah aku hapus.")
    else:
        await update.message.reply_text("Tidak ada memory yang perlu dihapus.")


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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("clearmemory", clearmemory_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

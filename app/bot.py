from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from app.config import TELEGRAM_BOT_TOKEN
from app.gemini import get_response
from app.database import init_db, save_message, get_recent_messages

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Halo! Saya asisten AI personal kamu.\n"
        "Powered by Gemini 2.5 Flash ⚡\n\n"
        "Coba tanya apa saja!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    save_message(user_id, "user", user_message)

    recent_messages = get_recent_messages(user_id, limit=10)
    print("RECENT MESSAGES:", recent_messages)

    await update.message.chat.send_action("typing")

    response = await get_response(user_id, user_message, recent_messages)

    save_message(user_id, "assistant", response)

    await update.message.reply_text(response)

def main():
    init_db()
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    print("🤖 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()

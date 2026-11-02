import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Loglama
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "9101317558:AAGt4hiYf7gVPrmCdtSPZ92zt4DyBpf4w0A"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Selam! Bot başarıyla aktif ve çalışıyor! 🚀')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"Dediklerini duyuyorum: {text}")

if __name__ == '__main__':
    # Telegram uygulamasını başlat
    application = ApplicationBuilder().token(TOKEN).build()

    # Komut ve mesaj yöneticileri
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), echo))

    print("Bot polling modunda başlatılıyor...")
    # Webhook'u temizle ve polling ile çalıştır
    application.run_polling()

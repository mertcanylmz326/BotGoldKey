import os
import logging
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# Logging ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token'ı doğrudan buraya gömüyoruz veya ortam değişkeninden alıyoruz
TOKEN = os.environ.get("TELEGRAM_TOKEN", "9101317558:AAEUpeDk9jCVgFrMm75UqKlUBePegs1C1Cs")

# 1. Flask Web Sunucusu (Render'ın uykuya atmasını önlemek için)
app = Flask('')

@app.route('/')
def home():
    return "Bot aktif ve çalışıyor! 🚀"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# 2. Telegram Bot Komutları
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(f"Selam {user_name}! Bot başarıyla aktif edildi ve çalışıyor. 🤖✨")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"Yazdın: {text}")

def main():
    # Flask sunucusunu arka planda başlat
    keep_alive()

    # Telegram Bot uygulamasını başlat
    application = ApplicationBuilder().token(TOKEN).build()

    # Komut ve mesaj yönlendiricileri
    application.add_handler(CommandHandler("start", start))
    
    logger.info("Bot başlatılıyor...")
    application.run_polling()

if __name__ == '__main__':
    main()

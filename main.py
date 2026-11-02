import os
import logging
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "9101317558:AAGt4hiYf7gVPrmCdtSPZ92zt4DyBpf4w0A"
PORT = int(os.environ.get("PORT", 8080))

app = Flask(__name__)
bot = Bot(token=TOKEN)

# Telegram Uygulamasını Başlat
telegram_app = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selam! Bot başarıyla aktif ve Render üzerinde çalışıyor! 🚀")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"Dediklerini duyuyorum: {text}")

# Komut ve mesaj yöneticilerini ekleyelim
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    """Telegram'dan gelen güncellemeleri webhook ile karşılar"""
    update = Update.de_json(request.get_json(force=True), bot)
    # Async fonksiyonu senkron Flask içinde çalıştırmak için
    import asyncio
    asyncio.run(telegram_app.process_update(update))
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot çalışıyor!", 200

if __name__ == "__main__":
    # Bot başlatıldığında Telegram'a webhook adresini otomatik tanıtmak istersen burayı kullanabilirsin
    # Render URL'niz belli olduktan sonra webhook ayarlanır.
    app.run(host="0.0.0.0", port=PORT)

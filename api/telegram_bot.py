import os
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from tools.router import ToolRouter
from db.controller.userController import check_if_user_exist_by_telegram, create_user_from_telegram
from utils.formatter import format_listings, get_listing_images
from utils.translator import translate_reply
from utils.transcriber import transcribe_audio
from utils.audio_downloader import download_attachment
import tempfile

router = ToolRouter()
LOGO_PATH = Path("Assets/logo.jpg")
MARKET_URL = "https://placeholder.moonso.app"  # replace when ready


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = str(user.id)

    exist, user_id = check_if_user_exist_by_telegram(telegram_id)

    if exist:
        from db.controller.userController import get_user_by_telegram
        db_user = get_user_by_telegram(telegram_id)
        name = db_user[2]  # name column
        await update.message.reply_text(
            f"👋 Welcome back {name}! How can I help you today?\n\n"
            "Just send me a message — I understand text and voice 🎙️"
        )
        return

    # new user — show welcome card
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌱 Create account", callback_data="register")],
        [InlineKeyboardButton("🔗 Link WhatsApp account", callback_data="link_account")],
        [InlineKeyboardButton("💬 Start chatting", callback_data="guest")],
        [InlineKeyboardButton("🛒 Open Marketplace", web_app={"url": MARKET_URL})],
    ])

    caption = (
        "🌾 *Moonso Link*\n"
        "_Your digital farmer assistant & marketplace_\n\n"
        "Buy and sell farm products, check market prices, "
        "and get farming advice — all from your phone.\n\n"
        "How would you like to get started?"
    )

    with open(LOGO_PATH, "rb") as logo:
        await update.message.reply_photo(
            photo=logo,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    telegram_id = str(user.id)

    if data == "register":
        context.user_data["state"] = "awaiting_name"
        await query.message.reply_text("Let's set up your account! 🌱\n\nWhat is your name?")

    elif data == "link_account":
        context.user_data["state"] = "awaiting_phone_link"
        await query.message.reply_text(
            "Enter the phone number linked to your WhatsApp account:\n"
            "_(include country code, e.g. +237651234567)_",
            parse_mode="Markdown"
        )

    elif data == "guest":
        context.user_data["state"] = "guest"
        await query.message.reply_text(
            "No problem! You can browse and ask questions freely 🌾\n\n"
            "To sell products or manage listings, you'll need an account. "
            "Just send /start anytime to create one."
        )
    elif data.startswith("region_"):
        region = data.replace("region_", "")
        reg_name = context.user_data.get("reg_name")
        reg_phone = context.user_data.get("reg_phone")
        user_id = create_user_from_telegram(telegram_id, reg_name, reg_phone, region)
        context.user_data["state"] = None
        await query.message.reply_text(
            f"✅ Account created! Welcome to Moonso Link {reg_name} 🌾\n\n"
            "You can now sell products, check prices and manage your listings.\n"
            "Just send me a message to get started!"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = str(user.id)
    name = user.full_name
    message = update.message.text
    state = context.user_data.get("state")

    # ── Registration flow ──────────────────────────────────────────────────
    if state == "awaiting_name":
        context.user_data["reg_name"] = message
        context.user_data["state"] = "awaiting_phone"
        await update.message.reply_text("What is your phone number? _(e.g. +237651234567)_", parse_mode="Markdown")
        return

    if state == "awaiting_phone":
        context.user_data["reg_phone"] = message
        context.user_data["state"] = "awaiting_region"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Centre", callback_data="region_Centre"),
             InlineKeyboardButton("Littoral", callback_data="region_Littoral")],
            [InlineKeyboardButton("Nord", callback_data="region_Nord"),
             InlineKeyboardButton("Sud", callback_data="region_Sud")],
            [InlineKeyboardButton("Ouest", callback_data="region_Ouest"),
             InlineKeyboardButton("Est", callback_data="region_Est")],
            [InlineKeyboardButton("Nord-Ouest", callback_data="region_Nord-Ouest"),
             InlineKeyboardButton("Sud-Ouest", callback_data="region_Sud-Ouest")],
            [InlineKeyboardButton("Adamaoua", callback_data="region_Adamaoua"),
             InlineKeyboardButton("Extreme-Nord", callback_data="region_Extreme-Nord")],
        ])
        await update.message.reply_text("Which region are you from?", reply_markup=keyboard)
        return

    if state == "awaiting_phone_link":
        from db.controller.userController import link_telegram_to_account
        result = link_telegram_to_account(message.strip(), telegram_id)
        if result["status"] == "ok":
            context.user_data["state"] = None
            await update.message.reply_text(f"✅ Account linked successfully! Welcome back {result['name']} 🌾")
        else:
            await update.message.reply_text("❌ No account found with that number. Try again or send /start to create one.")
        return

    # ── Guest or registered user ───────────────────────────────────────────
    exist, user_id = check_if_user_exist_by_telegram(telegram_id)

    if not exist and state != "guest":
        await update.message.reply_text("Send /start to get started 🌾")
        return

    if state == "guest":
        user_id = None

    result = router.handle(message, str(user_id) if user_id else None)
    await send_telegram_reply(update, result)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = str(user.id)
    state = context.user_data.get("state")

    exist, user_id = check_if_user_exist_by_telegram(telegram_id)
    if not exist and state != "guest":
        await update.message.reply_text("Send /start to get started 🌾")
        return

    # download voice file from Telegram
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    await file.download_to_drive(tmp.name)
    tmp.close()

    try:
        message = transcribe_audio(tmp.name)
        print(f"TELEGRAM TRANSCRIBED: {message}")
    finally:
        os.unlink(tmp.name)

    result = router.handle(message, str(user_id) if user_id else None)
    await send_telegram_reply(update, result)

async def send_telegram_reply(update: Update, result: dict):
    detected_lang = result.get("language", "en")

    if result.get("preview_image"):
        reply = translate_reply(result.get("message", "Done"), detected_lang)
        await update.message.reply_photo(
            photo=result["preview_image"],
            caption=reply,
            reply_markup=market_button()
        )

    elif "data" in result:
        data = result["data"]
        show_seller = result.get("show_seller", False)
        listings = data["listings"]
        text_listings = [l for l in listings if not l[8]]
        image_listings = get_listing_images(data, show_seller=show_seller)

        if text_listings:
            reply = format_listings({**data, "listings": text_listings}, show_seller=show_seller)
            reply = translate_reply(reply, detected_lang)
            keyboard = []
            if data["page"] > 1:
                keyboard.append(InlineKeyboardButton("◀ Previous", callback_data="prev"))
            if data["page"] < data["total_pages"]:
                keyboard.append(InlineKeyboardButton("Next ▶", callback_data="next"))
            keyboard_rows = [keyboard] if keyboard else []
            keyboard_rows.append([InlineKeyboardButton("🛒 Open Marketplace", web_app={"url": MARKET_URL})])
            await update.message.reply_text(reply, reply_markup=InlineKeyboardMarkup(keyboard_rows))

        for image_url, caption in image_listings:
            caption = translate_reply(caption, detected_lang)
            await update.message.reply_photo(photo=image_url, caption=caption)

    else:
        reply = translate_reply(result.get("message", "Done"), detected_lang)
        await update.message.reply_text(reply, reply_markup=market_button())

def setup_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("market", market))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

def market_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Open Marketplace", web_app={"url": MARKET_URL})]
    ])

async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛒 Open the Moonso Link marketplace:",
        reply_markup=market_button()
    )
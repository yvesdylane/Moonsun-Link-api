import os
import traceback
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from tools.router import ToolRouter
from db.controller.userController import check_if_user_exist_by_telegram, create_user_from_telegram
from utils.formatter import format_listings
from utils.translator import translate_reply
from utils.transcriber import transcribe_audio
from utils.audio_downloader import download_attachment
import tempfile

router = ToolRouter()
LOGO_PATH = Path("Assets/logo.jpg")
MARKET_URL = "https://placeholder.moonso.app"  # replace when ready`

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from utils.translator import translate_reply
    from langdetect import detect

    user = update.effective_user
    telegram_id = str(user.id)
    state = context.user_data.get("state")

    # Detect language: try from stored context, then Telegram's language_code, then default to en
    user_lang = context.user_data.get("user_lang")
    if not user_lang:
        # Check Telegram's language code
        telegram_lang = user.language_code
        if telegram_lang and telegram_lang.startswith("fr"):
            user_lang = "fr"
        else:
            user_lang = "en"
        context.user_data["user_lang"] = user_lang

    exist, user_id = check_if_user_exist_by_telegram(telegram_id)

    # Existing user or guest who already started - just acknowledge
    if exist or (state == "guest" and context.user_data.get("seen_welcome")):
        if exist:
            from db.controller.userController import get_user_by_telegram
            db_user = get_user_by_telegram(telegram_id)
            name = db_user[2]  # name column
            reply = translate_reply(
                f"👋 Welcome back {name}! How can I help you today?\n\n"
                "Just send me a message — I understand text and voice 🎙️",
                user_lang
            )
        else:
            reply = translate_reply(
                "👋 How can I help you today?\n\n"
                "Just send me a message — I understand text and voice 🎙️",
                user_lang
            )
        await update.message.reply_text(reply)
        return

    # New user — show full welcome card
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Link WhatsApp account", callback_data="link_account")],
        [InlineKeyboardButton("💬 Start chatting as guest", callback_data="guest")],
        [InlineKeyboardButton("🛒 Open Marketplace", web_app={"url": MARKET_URL})],
    ])

    caption = translate_reply(
        "🌾 *Moonso Link*\n"
        "_Your digital farmer assistant & marketplace_\n\n"
        "Buy and sell farm products, check market prices, "
        "and get farming advice — all from your phone.\n\n"
        "📝 To create an account: /create\n"
        "💬 To browse as guest: click below\n"
        "🔗 To link existing account: click below",
        user_lang
    )

    with open(LOGO_PATH, "rb") as logo:
        await update.message.reply_photo(
            photo=logo,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

async def create_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /create command - start registration flow"""
    from utils.translator import translate_reply

    user = update.effective_user
    telegram_id = str(user.id)
    user_lang = context.user_data.get("user_lang", "en")

    exist, user_id = check_if_user_exist_by_telegram(telegram_id)
    if exist:
        reply = translate_reply("You already have an account! Just send me a message 🌾", user_lang)
        await update.message.reply_text(reply)
        return

    context.user_data["state"] = "awaiting_name"

    reply = translate_reply(
        "Let's set up your account! 🌱\n\n"
        "What is your name?",
        user_lang
    )
    await update.message.reply_text(reply)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _handle_callback_inner(update, context)
    except Exception as e:
        print("=" * 60)
        print(f"UNHANDLED ERROR IN TELEGRAM CALLBACK: {e}")
        traceback.print_exc()
        print("=" * 60)
        try:
            await update.callback_query.message.reply_text(
                "Sorry, an error occurred on our side. Please try again later."
            )
        except Exception:
            pass

async def _handle_callback_inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    telegram_id = str(user.id)

    if data == "link_account":
        context.user_data["state"] = "awaiting_phone_link"
        await query.message.reply_text(
            "Enter the phone number linked to your WhatsApp account:\n"
            "_(include country code, e.g. +237651234567)_",
            parse_mode="Markdown"
        )

    elif data == "guest":
        from utils.translator import translate_reply

        context.user_data["state"] = "guest"
        context.user_data["seen_welcome"] = True

        # Try to detect language from previous interactions
        user_lang = context.user_data.get("reg_lang", "en")

        reply = translate_reply(
            "No problem! You can browse and ask questions freely 🌾\n\n"
            "To sell products or manage listings, you'll need an account. "
            "Send /create anytime to create one.",
            user_lang
        )
        await query.message.reply_text(reply)
    elif data == "link_yes":
        from utils.translator import translate_reply
        from db.connect import conn
        user_lang = context.user_data.get("user_lang", "en")

        existing_id = context.user_data.get("link_existing_id")
        telegram_number = context.user_data.get("reg_telegram_number")

        # Link telegram to existing account
        cur = conn.cursor()
        cur.execute("""
            UPDATE users
            SET telegram_id = %s, telegram_number = %s, updated_at = NOW()
            WHERE id = %s
        """, (telegram_id, telegram_number, existing_id))
        conn.commit()
        cur.close()

        context.user_data["state"] = None

        reply = translate_reply(
            "✅ Accounts linked successfully! Welcome back 🌾\n\n"
            "You can now use Moonso Link on both platforms.",
            user_lang
        )
        await query.message.reply_text(reply)

    elif data == "link_no":
        from utils.translator import translate_reply
        user_lang = context.user_data.get("user_lang", "en")

        reply = translate_reply(
            "❌ Cannot create a new account with an already registered number.\n\n"
            "Please use a different number or link to your existing account.",
            user_lang
        )
        context.user_data["state"] = None
        await query.message.reply_text(reply)

    elif data.startswith("region_"):
        from utils.translator import translate_reply
        user_lang = context.user_data.get("user_lang", "en")

        region = data.replace("region_", "")
        reg_name = context.user_data.get("reg_name")
        telegram_number = context.user_data.get("reg_telegram_number")

        # Create user with telegram_number (phone field stays NULL)
        user_id = create_user_from_telegram(telegram_id, reg_name, telegram_number, region)
        context.user_data["state"] = None

        reply = translate_reply(
            f"✅ Account created! Welcome to Moonso Link {reg_name} 🌾\n\n"
            "You can now browse and search products.\n"
            "To become a farmer and sell products, send: 'change my role to farmer'",
            user_lang
        )
        await query.message.reply_text(reply)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _handle_message_inner(update, context)
    except Exception as e:
        print("=" * 60)
        print(f"UNHANDLED ERROR IN TELEGRAM HANDLER: {e}")
        traceback.print_exc()
        print("=" * 60)
        await update.message.reply_text("Sorry, an error occurred on our side. Please try again later.")

async def _handle_message_inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = str(user.id)
    name = user.full_name
    message = update.message.text
    state = context.user_data.get("state")

    # Show typing indicator while processing
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # ── Registration flow ──────────────────────────────────────────────────
    if state == "awaiting_name":
        from utils.translator import translate_reply
        from telegram import KeyboardButton, ReplyKeyboardMarkup
        user_lang = context.user_data.get("user_lang", "en")

        context.user_data["reg_name"] = message.strip()
        context.user_data["state"] = "awaiting_telegram_number"

        # Ask for contact sharing
        contact_button = KeyboardButton("📱 Share my Telegram contact", request_contact=True)
        keyboard = ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True, resize_keyboard=True)

        reply = translate_reply(
            "📱 Share your Telegram phone number\n\n"
            "This helps us check if you have an account on other platforms (WhatsApp/SMS).",
            user_lang
        )
        await update.message.reply_text(reply, reply_markup=keyboard)
        return

    # Handle text-based region input during registration (allow skip)
    if state == "awaiting_region":
        from utils.translator import translate_reply
        user_lang = context.user_data.get("user_lang", "en")

        valid_regions = ["Centre", "Littoral", "Nord", "Sud", "Ouest", "Est",
                        "Nord-Ouest", "Sud-Ouest", "Adamaoua", "Extreme-Nord", "Extrême-Nord", "General", "Skip"]

        region_input = message.strip().title()
        if region_input == "Extreme-Nord":
            region_input = "Extreme-Nord"
        if region_input in ("Skip", "skip"):
            region_input = "General"

        if region_input in valid_regions:
            reg_name = context.user_data.get("reg_name")
            reg_phone = context.user_data.get("reg_phone")
            user_id = create_user_from_telegram(telegram_id, reg_name, reg_phone, region_input)
            context.user_data["state"] = None

            reply = translate_reply(
                f"✅ Account created! Welcome to Moonso Link {reg_name} 🌾\n\n"
                "You can now browse and search products.\n"
                "To become a farmer and sell products, send: 'change my role to farmer'",
                user_lang
            )
            await update.message.reply_text(reply)
        else:
            reply = translate_reply(
                "❌ Invalid region. Please choose from the buttons or type 'skip'",
                user_lang
            )
            await update.message.reply_text(reply)
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

    # If user doesn't exist and no state, automatically enable guest mode
    if not exist and state is None:
        context.user_data["state"] = "guest"
        state = "guest"

        # Detect and store user language on first message
        from langdetect import detect
        try:
            detected_lang = detect(message)
            if detected_lang in ("en", "fr"):
                context.user_data["user_lang"] = detected_lang
        except:
            pass

    if state == "guest":
        user_id = None

    result = router.handle(message, str(user_id) if user_id else None)

    # Handle notifications (seller, buyer, farmer)
    if result.get("seller_notification"):
        await send_telegram_notification(context, result["seller_notification"])

    if result.get("farmer_notification"):
        await send_telegram_notification(context, result["farmer_notification"])

    if result.get("buyer_notification"):
        await send_telegram_notification(context, result["buyer_notification"])

    await send_telegram_reply(update, result)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _handle_photo_inner(update, context)
    except Exception as e:
        print("=" * 60)
        print(f"UNHANDLED ERROR IN TELEGRAM PHOTO HANDLER: {e}")
        traceback.print_exc()
        print("=" * 60)
        await update.message.reply_text("Sorry, an error occurred on our side. Please try again later.")

async def _handle_photo_inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from utils.cloudinary_uploader import upload_image
    user = update.effective_user
    telegram_id = str(user.id)
    state = context.user_data.get("state")

    # Show typing indicator while processing photo
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    exist, user_id = check_if_user_exist_by_telegram(telegram_id)
    if not exist and state != "guest":
        await update.message.reply_text("Send /start to get started 🌾")
        return

    # Download photo from Telegram (get largest size)
    photo = update.message.photo[-1]  # Last item is largest size
    file = await context.bot.get_file(photo.file_id)

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    await file.download_to_drive(tmp.name)
    tmp.close()

    try:
        # Upload to Cloudinary
        image_url = upload_image(tmp.name)
        print(f"TELEGRAM IMAGE UPLOADED: {image_url}")

        # Get caption if user added one
        message = update.message.caption or ""

        # Handle image with router
        result = router.handle(message, str(user_id) if user_id else None, image_url=image_url)
        await send_telegram_reply(update, result)

    finally:
        os.unlink(tmp.name)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contact sharing during registration"""
    try:
        await _handle_contact_inner(update, context)
    except Exception as e:
        print("=" * 60)
        print(f"UNHANDLED ERROR IN TELEGRAM CONTACT HANDLER: {e}")
        traceback.print_exc()
        print("=" * 60)
        await update.message.reply_text("Sorry, an error occurred on our side. Please try again later.")

async def _handle_contact_inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from utils.translator import translate_reply
    from telegram import ReplyKeyboardRemove
    from db.connect import conn

    state = context.user_data.get("state")
    user_lang = context.user_data.get("user_lang", "en")
    telegram_id = str(update.effective_user.id)

    if state != "awaiting_telegram_number":
        return

    contact = update.message.contact
    phone = contact.phone_number

    if not phone.startswith("+"):
        phone = "+" + phone

    # Check if number exists on other platforms
    cur = conn.cursor()
    cur.execute("""
        SELECT telegram_number, whatsapp_number, phone, name, id
        FROM users
        WHERE telegram_number = %s OR whatsapp_number = %s OR phone = %s
    """, (phone, phone, phone))
    existing = cur.fetchone()
    cur.close()

    if existing:
        telegram_num, whatsapp_num, sms_phone, existing_name, existing_id = existing

        # Check which platform
        if telegram_num == phone:
            reply = translate_reply(
                f"❌ This Telegram number is already registered to '{existing_name}'.\n\n"
                "If this is your account, contact support.",
                user_lang
            )
            context.user_data["state"] = None
            await update.message.reply_text(reply, reply_markup=ReplyKeyboardRemove())
            return

        platform = "WhatsApp" if whatsapp_num == phone else "SMS"

        # Offer linking
        context.user_data["link_existing_id"] = str(existing_id)
        context.user_data["reg_telegram_number"] = phone
        context.user_data["state"] = "awaiting_link_confirmation"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, link them", callback_data="link_yes")],
            [InlineKeyboardButton("❌ No, create new", callback_data="link_no")],
        ])

        reply = translate_reply(
            f"📱 This number is already used on {platform} by '{existing_name}'.\n\n"
            f"Would you like to link your Telegram account to this existing account?",
            user_lang
        )
        await update.message.reply_text(reply, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(reply, reply_markup=keyboard)
        return

    # No existing account - continue with region selection
    context.user_data["reg_telegram_number"] = phone
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
        [InlineKeyboardButton("⏭️ Skip (All Cameroon)", callback_data="region_General")],
    ])

    reply = translate_reply(
        "📍 What is your primary region of operation?\n\n"
        "This helps buyers find products near them.\n"
        "Skip if you operate across all of Cameroon.",
        user_lang
    )
    await update.message.reply_text(reply, reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(reply, reply_markup=keyboard)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await _handle_voice_inner(update, context)
    except Exception as e:
        print("=" * 60)
        print(f"UNHANDLED ERROR IN TELEGRAM VOICE HANDLER: {e}")
        traceback.print_exc()
        print("=" * 60)
        await update.message.reply_text("Sorry, an error occurred on our side. Please try again later.")

async def _handle_voice_inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = str(user.id)
    state = context.user_data.get("state")

    # Show typing indicator while processing voice
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

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
    except Exception as e:
        print(f"TELEGRAM VOICE TRANSCRIPTION ERROR: {e}")
        traceback.print_exc()
        await update.message.reply_text("Sorry, could not process your voice message. Please try again.")
        return
    finally:
        os.unlink(tmp.name)

    result = router.handle(message, str(user_id) if user_id else None)

    # Handle notifications (seller, buyer, farmer)
    if result.get("seller_notification"):
        await send_telegram_notification(context, result["seller_notification"])

    if result.get("farmer_notification"):
        await send_telegram_notification(context, result["farmer_notification"])

    if result.get("buyer_notification"):
        await send_telegram_notification(context, result["buyer_notification"])

    await send_telegram_reply(update, result)

async def send_telegram_notification(context: ContextTypes.DEFAULT_TYPE, notification: dict):
    """
    Send notification to a Telegram user.

    The router now passes telegram_id directly in notification['telegram_id'].
    """
    from db.connect import conn
    from utils.translator import translate_reply

    telegram_id = notification.get("telegram_id")
    message = notification.get("message")

    if not telegram_id or not message:
        print(f"TELEGRAM NOTIFICATION SKIPPED: Missing telegram_id or message")
        return

    # Get user's language preference
    cur = conn.cursor()
    cur.execute("""
        SELECT lang FROM users WHERE telegram_id = %s
    """, (telegram_id,))
    result = cur.fetchone()
    cur.close()

    lang = result[0] if result else "en"

    # Translate notification message
    message = translate_reply(message, lang)

    try:
        await context.bot.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode="Markdown"
        )
        print(f"TELEGRAM NOTIFICATION SENT: {telegram_id}")
    except Exception as e:
        print(f"TELEGRAM NOTIFICATION ERROR to {telegram_id}: {e}")

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
        reply = format_listings(data, show_seller=show_seller)
        reply = translate_reply(reply, detected_lang)
        keyboard = []
        if data["page"] > 1:
            keyboard.append(InlineKeyboardButton("◀ Previous", callback_data="prev"))
        if data["page"] < data["total_pages"]:
            keyboard.append(InlineKeyboardButton("Next ▶", callback_data="next"))
        keyboard_rows = [keyboard] if keyboard else []
        keyboard_rows.append([InlineKeyboardButton("🛒 Open Marketplace", web_app={"url": MARKET_URL})])
        await update.message.reply_text(reply, reply_markup=InlineKeyboardMarkup(keyboard_rows))

    else:
        reply = translate_reply(result.get("message", "Done"), detected_lang)
        await update.message.reply_text(reply, reply_markup=market_button())

def setup_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create", create_account))
    app.add_handler(CommandHandler("market", market))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
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
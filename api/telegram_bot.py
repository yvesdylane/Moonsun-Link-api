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
            name = db_user['name']
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
        print(f"reply:{reply}")
        await update.message.reply_text(reply)
        return

    # New user — show full welcome card
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Link WhatsApp account", callback_data="link_account")],
        [InlineKeyboardButton("💬 Start chatting as guest", callback_data="guest")],
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
        from utils.translator import translate_reply
        user_lang = context.user_data.get("user_lang", "en")

        # Check if we have their Telegram number from registration
        telegram_number = context.user_data.get("reg_telegram_number")

        if telegram_number:
            context.user_data["link_phone"] = telegram_number
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Use this number", callback_data="confirm_link_number")],
                [InlineKeyboardButton("📝 Enter different number", callback_data="enter_link_number")],
            ])
            await query.message.reply_text(
                f"Your Telegram number is: {telegram_number}\n\n"
                "Would you like to link this number, or enter a different WhatsApp number?",
                reply_markup=keyboard
            )
        else:
            context.user_data["state"] = "awaiting_phone_link"
            await query.message.reply_text(
                "Enter the phone number linked to your WhatsApp account:\n"
                "_(include country code, e.g. +237651234567)_",
                parse_mode="Markdown"
            )

    elif data == "confirm_link_number":
        await _start_verification_for_phone(context, query)

    elif data == "enter_link_number":
        context.user_data["state"] = "awaiting_phone_link"
        await query.message.reply_text(
            "Enter the WhatsApp number you want to link:\n"
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

        # Get the phone number of the existing WhatsApp account
        cur = conn.cursor()
        cur.execute("""
            SELECT whatsapp_number, whatsapp_chat_id FROM users WHERE id = %s
        """, (existing_id,))
        row = cur.fetchone()
        cur.close()

        if not row or not row['whatsapp_number']:
            await query.message.reply_text(translate_reply(
                "❌ Could not find the WhatsApp account details. Please try again.",
                user_lang
            ))
            return

        whatsapp_number = row['whatsapp_number']; whatsapp_chat_id = row['whatsapp_chat_id']

        if not whatsapp_chat_id:
            await query.message.reply_text(translate_reply(
                "❌ That account doesn't have an active WhatsApp connection.\n\n"
                "Please use Moonso Link on WhatsApp first.",
                user_lang
            ))
            return

        # Store context for the verification step
        context.user_data["link_target_phone"] = whatsapp_number
        context.user_data["link_target_user_id"] = existing_id
        context.user_data["link_from_registration"] = True
        context.user_data["link_reg_telegram_number"] = telegram_number

        # Send verification code
        from db.controller.userController import generate_linking_code
        from utils.whatsapp import send_whatsapp_reply
        code = generate_linking_code(existing_id)
        message = f"🔐 Your Moonso Link verification code is: {code}\n\nEnter this code in Telegram to complete account linking. Code expires in 5 minutes."
        send_whatsapp_reply(whatsapp_chat_id, message)

        context.user_data["state"] = "awaiting_verification_code"

        await query.message.reply_text(translate_reply(
            f"✅ Verification code sent to {whatsapp_number} via WhatsApp!\n\n"
            "Enter the 6-digit code in Telegram to complete linking.\n"
            "_Code expires in 5 minutes._\n\n"
            "To resend the code, type: /resend",
            user_lang
        ), parse_mode="Markdown")

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

async def _start_verification_for_phone(context: ContextTypes.DEFAULT_TYPE,
                                        source: str = None,
                                        phone: str = None) -> tuple:
    """
    Look up a WhatsApp number, send verification code, set state.

    Args:
        context: Telegram context.user_data
        source: 'callback' (from link_yes/confirm_link_number) or 'text' (from awaiting_phone_link)
        phone: phone number if already known, else read from context

    Returns:
        (success: bool, reply_text: str)
    """
    from db.controller.userController import find_whatsapp_user_by_number, generate_linking_code
    from utils.whatsapp import send_whatsapp_reply
    from utils.translator import translate_reply

    user_lang = context.user_data.get("user_lang", "en")

    if not phone:
        phone = context.user_data.get("link_phone", "")

    phone = phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    # Look up the number
    user = find_whatsapp_user_by_number(phone)
    if user is None:
        context.user_data["state"] = None
        return (False, translate_reply(
            f"❌ No Moonso account found with WhatsApp number {phone}.\n\n"
            "Make sure you have used Moonso Link on WhatsApp first.",
            user_lang
        ))

    if user.get("status") == "no_chat_id":
        context.user_data["state"] = None
        return (False, translate_reply(
            f"❌ The number {phone} doesn't have an active WhatsApp connection on Moonso.\n\n"
            "Please use Moonso Link on WhatsApp first, then try linking.",
            user_lang
        ))

    # Generate and store verification code
    code = generate_linking_code(user["id"])
    context.user_data["link_target_phone"] = phone
    context.user_data["link_target_user_id"] = user["id"]
    context.user_data["state"] = "awaiting_verification_code"

    # Send code to their WhatsApp
    message = f"🔐 Your Moonso Link verification code is: {code}\n\nEnter this code in Telegram to complete account linking. Code expires in 5 minutes."
    send_whatsapp_reply(user["whatsapp_chat_id"], message)

    return (True, translate_reply(
        f"✅ Verification code sent to {phone} via WhatsApp!\n\n"
        "Enter the 6-digit code in Telegram to complete linking.\n"
        "_Code expires in 5 minutes._\n\n"
        "To resend the code, type: /resend",
        user_lang
    ))


async def resend_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resend command — resend verification code."""
    try:
        await _resend_code_inner(update, context)
    except Exception as e:
        print(f"RESEND CODE ERROR: {e}")
        traceback.print_exc()
        await update.message.reply_text("Sorry, an error occurred. Please start the linking process again from /start.")


async def _resend_code_inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from db.controller.userController import generate_linking_code, find_whatsapp_user_by_number
    from utils.whatsapp import send_whatsapp_reply
    from utils.translator import translate_reply

    user_lang = context.user_data.get("user_lang", "en")
    state = context.user_data.get("state")

    if state != "awaiting_verification_code":
        await update.message.reply_text(translate_reply(
            "❌ No active verification in progress.\n\n"
            "To start linking your account, send /start and click 'Link WhatsApp account'.",
            user_lang
        ))
        return

    target_phone = context.user_data.get("link_target_phone")
    target_user_id = context.user_data.get("link_target_user_id")

    if not target_phone or not target_user_id:
        context.user_data["state"] = None
        await update.message.reply_text(translate_reply(
            "❌ Verification session expired. Please start linking again from /start.",
            user_lang
        ))
        return

    # Generate new code
    code = generate_linking_code(target_user_id)

    # Send to WhatsApp
    user = find_whatsapp_user_by_number(target_phone)
    if not user or user.get("status") != "ok":
        await update.message.reply_text(translate_reply(
            "❌ Could not send the code. Please start linking again from /start.",
            user_lang
        ))
        return

    message = f"🔐 Your new Moonso Link verification code is: {code}\n\nEnter this code in Telegram to complete account linking. Code expires in 5 minutes."
    send_whatsapp_reply(user["whatsapp_chat_id"], message)

    await update.message.reply_text(translate_reply(
        f"✅ New code sent to {target_phone}!\n\nEnter the 6-digit code in Telegram.\n_Code expires in 5 minutes._",
        user_lang
    ), parse_mode="Markdown")


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
        context.user_data["link_phone"] = message.strip()
        success, reply = await _start_verification_for_phone(context, source="text")
        await update.message.reply_text(reply, parse_mode="Markdown")
        return

    if state == "awaiting_verification_code":
        from db.controller.userController import verify_linking_code, find_whatsapp_user_by_number, link_and_merge_accounts
        from utils.whatsapp import send_whatsapp_reply
        from utils.translator import translate_reply
        user_lang = context.user_data.get("user_lang", "en")

        target_phone = context.user_data.get("link_target_phone", "")
        entered_code = message.strip()

        # Allow 6-digit codes only
        if not entered_code.isdigit() or len(entered_code) != 6:
            await update.message.reply_text(translate_reply(
                "❌ Please enter the 6-digit verification code sent to your WhatsApp.\n\n"
                "To resend the code, type: /resend",
                user_lang
            ))
            return

        result = verify_linking_code(target_phone, entered_code)

        if result["status"] == "error":
            await update.message.reply_text(translate_reply(result["message"], user_lang))
            return

        # Code verified successfully — complete linking
        whatsapp_user_id = result["id"]

        # Check if Telegram user already has a separate DB account (merge needed)
        from db.controller.userController import get_user_by_telegram
        telegram_user = get_user_by_telegram(telegram_id)
        telegram_user_id_to_merge = str(telegram_user['id']) if telegram_user else None

        # Get the Telegram number if available
        telegram_number = context.user_data.get("reg_telegram_number")

        # Link and optionally merge
        link_result = link_and_merge_accounts(
            whatsapp_user_id=whatsapp_user_id,
            telegram_id=telegram_id,
            telegram_number=telegram_number,
            telegram_user_id_to_merge=telegram_user_id_to_merge
        )

        context.user_data["state"] = None

        # Send confirmation to WhatsApp
        try:
            user_info = find_whatsapp_user_by_number(target_phone)
            if user_info and user_info.get("status") == "ok":
                send_whatsapp_reply(
                    user_info["whatsapp_chat_id"],
                    "✅ Your Telegram account has been linked to Moonso Link!\n\nYou can now use Moonso Link on both platforms."
                )
        except Exception:
            pass

        await update.message.reply_text(translate_reply(
            f"✅ Accounts linked successfully! Welcome back {result['name']} 🌾\n\n"
            "You can now use Moonso Link on both Telegram and WhatsApp.",
            user_lang
        ), parse_mode="Markdown")
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

    print(f"\n===== TELEGRAM DEBUG =====")
    print(f"Platform: Telegram")
    print(f"Telegram ID: {telegram_id}")
    print(f"DB User UUID: {user_id}")
    from db.controller.userController import get_user_info
    db_user = get_user_info(str(user_id)) if user_id else None
    if db_user:
        print(f"DB User verified field: '{db_user.verified}'")
        print(f"DB User role: {db_user.role}")
        print(f"DB User name: {db_user.name}")
    print(f"User message: {message}")
    out = result.get("message", "") or result.get("data", "")
    print(f"Bot reply (first 500): {str(out)[:500]}")
    print(f"Result keys: {list(result.keys())}")
    print(f"==========================\n")

    # Handle notifications (seller, buyer, farmer)
    if result.get("seller_notification"):
        await send_telegram_notification(context, result["seller_notification"])

    if result.get("farmer_notification"):
        await send_telegram_notification(context, result["farmer_notification"])

    if result.get("buyer_notification"):
        await send_telegram_notification(context, result["buyer_notification"])

    await send_telegram_reply(update, result)

    # Log message exchange
    if user_id:
        from db.controller.messageLogController import log_message_exchange
        detected_lang = result.get("language", "en")
        full_reply = extract_reply_text(result)
        log_message_exchange(
            user_id=str(user_id),
            incoming=message,
            outgoing=full_reply,
            intent=result.get("intent", {}).get("intent", "unknown") if isinstance(result.get("intent"), dict) else "unknown",
            platform="telegram"
        )

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

        # Log message exchange
        if user_id:
            from db.controller.messageLogController import log_message_exchange
            incoming_text = f"[Photo] {message}" if message else "[Photo]"
            full_reply = extract_reply_text(result)
            log_message_exchange(
                user_id=str(user_id),
                incoming=incoming_text,
                outgoing=full_reply,
                intent=result.get("intent", {}).get("intent", "unknown") if isinstance(result.get("intent"), dict) else "unknown"
            )

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
        telegram_num = existing['telegram_number']
        whatsapp_num = existing['whatsapp_number']
        sms_phone = existing['phone']
        existing_name = existing['name']
        existing_id = existing['id']

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

    # Log message exchange (for voice transcriptions)
    if user_id:
        from db.controller.messageLogController import log_message_exchange
        full_reply = extract_reply_text(result)
        log_message_exchange(
            user_id=str(user_id),
            incoming=message,
            outgoing=full_reply,
            intent=result.get("intent", {}).get("intent", "unknown") if isinstance(result.get("intent"), dict) else "unknown",
            platform="telegram"
        )

def extract_reply_text(result: dict) -> str:
    """Extract reply text from router result for logging"""
    if "data" in result:
        # Listing data - format a summary
        data = result["data"]
        return f"Listings response: {data['total']} results (page {data['page']}/{data['total_pages']})"
    elif result.get("preview_image"):
        return result.get("message", "Image sent")
    else:
        return result.get("message", "Done")

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

    lang = result['lang'] if result else "en"

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
        await update.message.reply_text(reply, reply_markup=InlineKeyboardMarkup(keyboard_rows))

    else:
        reply = translate_reply(result.get("message", "Done"), detected_lang)
        await update.message.reply_text(reply)

def setup_handlers(app: Application):
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("create", create_account, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("resend", resend_code, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.CONTACT & filters.ChatType.PRIVATE, handle_contact))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))
    app.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, handle_voice))
from fastapi import FastAPI, Request
from pydantic import BaseModel
from contextlib import asynccontextmanager
from tools.router import ToolRouter
from db.controller.userController import check_if_user_exist, create_user_from_whatsapp
from db.controller.messageLogController import log_message_exchange
from utils.whatsapp import send_whatsapp_reply, send_whatsapp_image
from utils.formatter import format_listings
from utils.translator import translate_reply
from utils.transcriber import transcribe_audio
from utils.audio_downloader import download_voice_note, download_attachment
from utils.cloudinary_uploader import upload_image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import asyncio
import os
import traceback


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup: Open async database pool
    from db.connect import async_pool
    await async_pool.open()
    print("✅ Async database pool opened")

    # Start Telegram bot
    from api.telegram_bot import setup_handlers
    setup_handlers(telegram_app)
    await telegram_app.initialize()
    await telegram_app.start()
    print("✅ Telegram bot ready via webhook")

    yield

    # Shutdown
    await telegram_app.stop()
    await async_pool.close()
    print("✅ Async database pool closed")


app = FastAPI(lifespan=lifespan)
router = ToolRouter()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# build telegram app once at startup
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

class MessageRequest(BaseModel):
    message: str

@app.get("/")
def home():
    return {"message": "Server working. Wellcome to moonsu"}


@app.post("/whatsapp")
async def webhook(request: Request):
    chat_id = None
    try:
        data = await request.json()
        print(data)
        if data.get("event") != "message_received":
            return {"status": "received"}
        chat_id = data.get("chat_id")
        return await _handle_webhook(data)
    except Exception as e:
        print("=" * 60)
        print(f"UNHANDLED ERROR IN WHATSAPP WEBHOOK: {e}")
        traceback.print_exc()
        print("=" * 60)
        if chat_id:
            send_whatsapp_reply(chat_id, "Sorry, an error occurred on our side. Please try again later.")
        return {"status": "error"}

async def _handle_webhook(data: dict):
    if data.get("is_sender"):
        return {"status": "ignored"}

    phone = data["sender"]["attendee_specifics"]["phone_number"]
    name = data["sender"]["attendee_name"]
    chat_id = data["chat_id"]

    # get message text
    message = data.get("message")
    message_id = data.get("message_id")
    print(f"EVENT message_id={message_id} is_sender={data.get('is_sender')}")

    # handle voice note
    image_url = None
    attachments = data.get("attachments", [])

    voice = next((a for a in attachments if a.get("voice_note")), None)
    image = next((a for a in attachments if a.get("attachment_type") in ("file", "img")), None)

    # handle voice
    if not message and voice:
        try:
            file_path = download_attachment(voice["attachment_id"], data["message_id"], suffix=".ogg")
            message = transcribe_audio(file_path)
            os.unlink(file_path)
            print(f"TRANSCRIBED: {message}")
        except Exception as e:
            print(f"VOICE PROCESSING ERROR: {e}")
            traceback.print_exc()
            send_whatsapp_reply(chat_id, "Sorry, could not process your voice message. Please try again.")
            return {"status": "error", "detail": "voice_processing_failed"}

    # handle image
    if image:
        try:
            attachment_name = image.get("attachment_name", "image.jpg")
            suffix = "." + attachment_name.rsplit(".", 1)[-1]
            file_path = download_attachment(image["attachment_id"], data["message_id"], suffix=suffix)
            image_url = upload_image(file_path)
            os.unlink(file_path)
            print(f"IMAGE URL: {image_url}")
        except Exception as e:
            print(f"IMAGE PROCESSING ERROR: {e}")
            traceback.print_exc()

    if not message:
        return {"status": "ignored"}

    exist, user_id = check_if_user_exist(phone)
    if not exist:
        # Check if this number exists on other platforms (Telegram or SMS)
        from db.controller.userController import check_cross_platform_account
        cross_platform = check_cross_platform_account(phone)

        if cross_platform:
            # Link WhatsApp to existing account
            from db.controller.userController import link_whatsapp_to_existing
            user_id = link_whatsapp_to_existing(cross_platform["user_id"], phone, chat_id)
            print(f"WHATSAPP LINKED TO EXISTING ACCOUNT: {user_id} (from {cross_platform['platform']})")
        else:
            # Create new account
            user_id = create_user_from_whatsapp(phone, name, chat_id)
    else:
        # Update chat_id if not already set
        from db.controller.userController import update_user_chat_id
        update_user_chat_id(str(user_id), chat_id)

    result = router.handle(message, str(user_id), image_url=image_url)
    print(f"MESSAGE: {message}")
    print(f"RESULT: {result}")

    # Handle notifications (seller, buyer, farmer)
    if result.get("seller_notification"):
        seller_notif = result["seller_notification"]
        if seller_notif.get("whatsapp_chat_id") and seller_notif.get("message"):
            send_whatsapp_reply(seller_notif["whatsapp_chat_id"], seller_notif["message"])
            print(f"SELLER NOTIFIED (WhatsApp): {seller_notif['whatsapp_chat_id']}")

    if result.get("farmer_notification"):
        farmer_notif = result["farmer_notification"]
        if farmer_notif.get("chat_id") and farmer_notif.get("message"):
            send_whatsapp_reply(farmer_notif["chat_id"], farmer_notif["message"])
            print(f"FARMER NOTIFIED: {farmer_notif['chat_id']}")

    if result.get("buyer_notification"):
        buyer_notif = result["buyer_notification"]
        if buyer_notif.get("chat_id") and buyer_notif.get("message"):
            send_whatsapp_reply(buyer_notif["chat_id"], buyer_notif["message"])
            print(f"BUYER NOTIFIED: {buyer_notif['chat_id']}")

    # reply section
    detected_lang = result.get("language", "en")
    full_reply = ""

    if result.get("preview_image"):
        reply = result.get("message", "Done")
        reply = translate_reply(reply, detected_lang)
        send_whatsapp_image(chat_id, result["preview_image"], caption=reply)
        full_reply = reply
    elif "data" in result:
        listings_data = result["data"]
        show_seller = result.get("show_seller", False)
        market_avg = result.get("market_avg")
        reply = format_listings(listings_data, show_seller=show_seller, market_avg=market_avg)

        # Add market price header or message prefix if provided
        if result.get("market_price_header"):
            reply = result["market_price_header"] + reply
        elif result.get("message_prefix"):
            reply = result["message_prefix"] + reply

        reply = translate_reply(reply, detected_lang)
        send_whatsapp_reply(chat_id, reply)
        full_reply = reply
    else:
        reply = result.get("message", "Done")
        reply = translate_reply(reply, detected_lang)
        send_whatsapp_reply(chat_id, reply)
        full_reply = reply

    # log the exchange
    log_message_exchange(
        user_id=str(user_id),
        incoming=message,
        outgoing=full_reply,
        intent=result.get("intent", {}).get("intent", "unknown") if isinstance(result.get("intent"),
                                                                               dict) else "unknown"
    )

    return {"status": "received", "response": result}

@app.post("/chat")
def chat(request: MessageRequest):
    result = router.handle(request.message)
    return result

@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    print(data)
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}
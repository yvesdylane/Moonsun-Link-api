from fastapi import FastAPI, Request
from pydantic import BaseModel
from tools.router import ToolRouter
from db.controller.userController import check_if_user_exist, create_user_from_whatsapp
from db.controller.messageLogController import log_message_exchange
from utils.whatsapp import send_whatsapp_reply, send_whatsapp_image
from utils.formatter import format_listings, get_listing_images
from utils.translator import translate_reply
from utils.transcriber import transcribe_audio
from utils.audio_downloader import download_voice_note, download_attachment
from utils.cloudinary_uploader import upload_image
import os

app = FastAPI()
router = ToolRouter()

class MessageRequest(BaseModel):
    message: str

@app.get("/")
def home():
    return {"message": "Server working. Wellcome to moonsu"}


@app.post("/whatsapp")
async def webhook(request: Request):
    data = await request.json()
    print(data)
    if data["event"] == "message_received":
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
            file_path = download_attachment(voice["attachment_id"], data["message_id"], suffix=".ogg")
            message = transcribe_audio(file_path)
            os.unlink(file_path)
            print(f"TRANSCRIBED: {message}")

        # handle image
        if image:
            attachment_name = image.get("attachment_name", "image.jpg")
            suffix = "." + attachment_name.rsplit(".", 1)[-1]
            file_path = download_attachment(image["attachment_id"], data["message_id"], suffix=suffix)
            image_url = upload_image(file_path)
            os.unlink(file_path)
            print(f"IMAGE URL: {image_url}")

        if not message:
            return {"status": "ignored"}

        exist, user_id = check_if_user_exist(phone)
        if not exist:
            user_id = create_user_from_whatsapp(phone, name)

        result = router.handle(message, str(user_id), image_url=image_url)
        print(f"MESSAGE: {message}")
        print(f"RESULT: {result}")

        # reply section
        detected_lang = result.get("language", "en")
        if result.get("preview_image"):
            reply = result.get("message", "Done")
            reply = translate_reply(reply, detected_lang)
            send_whatsapp_image(chat_id, result["preview_image"], caption=reply)
        elif "data" in result:
            data = result["data"]
            show_seller = result.get("show_seller", False)
            listings = data["listings"]
            image_listings = get_listing_images(data, show_seller=show_seller)
            text_listings = [l for l in listings if not l[8]]

            if text_listings:
                text_data = {**data, "listings": text_listings}
                reply = format_listings(text_data, show_seller=show_seller)
                reply = translate_reply(reply, detected_lang)
                send_whatsapp_reply(chat_id, reply)

            for image_url, caption in image_listings:
                caption = translate_reply(caption, detected_lang)
                send_whatsapp_image(chat_id, image_url, caption=caption)

            full_reply = format_listings(data, show_seller=show_seller)
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

    return {"status": "received"}

@app.post("/chat")
def chat(request: MessageRequest):
    result = router.handle(request.message)
    return result
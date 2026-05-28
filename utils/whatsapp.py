import requests
import os
from dotenv import load_dotenv

load_dotenv()

UNIPILE_URL = os.getenv("UNIPILE_DSN")
UNIPILE_TOKEN = os.getenv("UNIPILE_API_KEY")


def send_whatsapp_reply(chat_id: str, message: str):
    url = f"{UNIPILE_URL}/api/v1/chats/{chat_id}/messages"
    headers = {"X-API-KEY": UNIPILE_TOKEN}
    data = {"text": message}
    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        print(f"WhatsApp send response: {response.status_code}")
        if response.status_code != 200:
            print(f"WhatsApp send error: {response.text}")
        return response.json()
    except Exception as e:
        print(f"WHATSAPP SEND ERROR: {e}")
        return {"status": "error", "error": str(e)}


def send_whatsapp_image(chat_id: str, image_url: str, caption: str = ""):
    import tempfile

    # Download image from Cloudinary
    img_response = requests.get(image_url)

    suffix = "." + image_url.rsplit(".", 1)[-1].split("?")[0]

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(img_response.content)
    tmp.close()

    url = f"{UNIPILE_URL}/api/v1/chats/{chat_id}/messages"

    headers = {
        "X-API-KEY": UNIPILE_TOKEN
    }

    try:
        with open(tmp.name, "rb") as f:

            files = {
                "attachments": f
            }

            data = {
                "text": caption
            }

            response = requests.post(
                url,
                headers=headers,
                files=files,
                data=data
            )

        print(response.status_code)
        print(response.text)

        return response.json()

    finally:
        os.unlink(tmp.name)
import requests
import os
from dotenv import load_dotenv

load_dotenv()

UNIPILE_URL = os.getenv("UNIPILE_DSN")
UNIPILE_TOKEN = os.getenv("UNIPILE_API_KEY")

def send_whatsapp_reply(chat_id: str, message: str):
    url = f"{UNIPILE_URL}/api/v1/chats/{chat_id}/messages"
    headers = {
        "accept": "application/json",
        "X-API-KEY": UNIPILE_TOKEN
    }
    data = {"text": message}
    response = requests.post(url, headers=headers, data=data)
    return response.json()
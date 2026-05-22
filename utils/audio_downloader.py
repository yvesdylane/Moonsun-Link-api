import requests
import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

UNIPILE_URL = os.getenv("UNIPILE_DSN")
UNIPILE_TOKEN = os.getenv("UNIPILE_API_KEY")


def download_voice_note(attachment_id: str, message_id: str) -> str:
    url = f"{UNIPILE_URL}/api/v1/messages/{message_id}/attachments/{attachment_id}"
    headers = {"X-API-KEY": UNIPILE_TOKEN}

    response = requests.get(url, headers=headers)
    print(f"CALLING URL: {url}")
    print(f"DOWNLOAD STATUS: {response.status_code}")

    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.write(response.content)
    tmp.close()
    return tmp.name
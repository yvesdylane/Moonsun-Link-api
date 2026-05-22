import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_image(file_path: str) -> str | None:
    print(f"CLOUD NAME: '{os.getenv('CLOUDINARY_CLOUD_NAME')}'")
    try:
        result = cloudinary.uploader.upload(file_path, folder="moonso/listings")
        return result["secure_url"]
    except Exception as e:
        print(f"CLOUDINARY ERROR: {e}")
        return None
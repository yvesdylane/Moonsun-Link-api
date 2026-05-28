from PIL import Image
import io
import os

MAX_WIDTH = 1200
MAX_HEIGHT = 1200
QUALITY = 75
MAX_SIZE_BYTES = 500 * 1024  # 500KB target

def compress_image(file_path: str) -> bytes:
    img = Image.open(file_path)
    img_format = img.format or "JPEG"
    if img_format.upper() == "PNG":
        img_format = "PNG"
    else:
        img_format = "JPEG"

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)

    output = io.BytesIO()
    quality = QUALITY

    while True:
        output.seek(0)
        output.truncate()
        img.save(output, format=img_format, quality=quality, optimize=True)
        if output.tell() <= MAX_SIZE_BYTES or quality <= 20:
            break
        quality -= 10

    return output.getvalue()

def compress_and_save(file_path: str) -> str:
    compressed = compress_image(file_path)
    with open(file_path, "wb") as f:
        f.write(compressed)
    return file_path

def compress_image_from_bytes(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data))
    img_format = img.format or "JPEG"
    if img_format.upper() == "PNG":
        img_format = "PNG"
    else:
        img_format = "JPEG"

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)

    output = io.BytesIO()
    quality = QUALITY

    while True:
        output.seek(0)
        output.truncate()
        img.save(output, format=img_format, quality=quality, optimize=True)
        if output.tell() <= MAX_SIZE_BYTES or quality <= 20:
            break
        quality -= 10

    return output.getvalue()

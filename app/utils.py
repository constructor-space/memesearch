from typing import Optional

import cv2
import easyocr
from sqlalchemy import select
from PIL import Image as PILImage
from imagehash import phash

from app.db import session, fetch_val
from app.models import Channel, Image
from app.config import IMAGES_DIR

eocr = easyocr.Reader(['ru', 'en'])


async def get_or_create_channel(id_: int, title: str, username: str) -> Channel:
    """Get existing channel or create a new one"""
    channel = await Channel.get(id_)
    if not channel:
        channel = Channel(id=id_, name=title, username=username)
        session.add(channel)
        await session.flush()
    return channel


async def process_image(
    photo_path: str, ocr_result: Optional[str] = None
) -> tuple[str, str]:
    """Process an image file and return its hash and text content"""
    # Ensure images directory exists
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Calculate phash of the image
    with open(photo_path, 'rb') as f:
        file_content = f.read()
    image_phash = str(phash(PILImage.open(photo_path)))

    # Copy image to the images directory with hash as name
    target_path = IMAGES_DIR / f'{image_phash}.jpg'
    if not target_path.exists():
        with open(target_path, 'wb') as f:
            f.write(file_content)

    # If ocr_result is provided, use it
    if ocr_result:
        return image_phash, ocr_result

    # Convert image for OCR
    image_cv2 = cv2.cvtColor(cv2.imread(photo_path), cv2.COLOR_BGR2RGB)

    # Run OCR
    ocr_result = eocr.readtext(image_cv2)
    ocr_text = '\n'.join([item[1] for item in ocr_result])

    return image_phash, ocr_text or 'No text detected'


async def get_or_create_image(image_phash: str, text: str) -> Image:
    """Get existing image or create a new one"""
    image = await fetch_val(select(Image).where(Image.phash == image_phash))

    if not image:
        image = Image(phash=image_phash, text=text)
        session.add(image)
        await session.flush()

    return image

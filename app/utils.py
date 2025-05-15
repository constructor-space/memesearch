import shutil
from pathlib import Path
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

def calculate_phash(image_path: str) -> str:
    """Calculate perceptual hash of an image"""
    with open(image_path, 'rb') as f:
        file_content = f.read()
    return str(phash(PILImage.open(image_path)))

def save_image(image_path: str, phash: str) -> Path:
    """Save image to the IMAGES_DIR with its phash as filename"""
    target_path = IMAGES_DIR / f'{phash}.jpg'
    if not target_path.exists():
        shutil.copy(image_path, target_path)
    return target_path

def process_image(
    photo_path: str, ocr_result: Optional[str] = None
) -> str:
    """Process an image file and return its hash and text content"""
    # Ensure images directory exists
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # If ocr_result is provided, use it
    if ocr_result:
        return ocr_result

    # Convert image for OCR
    image_cv2 = cv2.cvtColor(cv2.imread(photo_path), cv2.COLOR_BGR2RGB)

    # Run OCR
    ocr_result = eocr.readtext(image_cv2)
    ocr_text = '\n'.join([item[1] for item in ocr_result])

    return ocr_text or 'No text detected'


async def get_or_create_image(image_phash: str, text: str) -> Image:
    """Get existing image or create a new one"""
    image = await fetch_val(select(Image).where(Image.phash == image_phash))

    if not image:
        image = Image(phash=image_phash, text=text)
        session.add(image)
        await session.flush()

    return image

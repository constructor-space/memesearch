import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import cv2
import easyocr
from sqlalchemy import select
from tqdm import tqdm
from PIL import Image as PILImage
from imagehash import phash

from app.db import new_session, session, fetch_val
from app.models.channel import Channel, ChannelMessage
from app.models.image import Image
from app.config import IMAGES_DIR
from telethon.tl.types import Channel as ChannelTg

eocr = easyocr.Reader(['ru', 'en'])


async def get_or_create_channel(channel_tg: ChannelTg) -> Channel:
    """Get existing channel or create a new one"""
    channel = await Channel.get(channel_tg.id)
    if not channel:
        channel = Channel(id=channel_tg.id, name=channel_tg.title, username=channel_tg.username)
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


async def import_from_json(base_dir: Path, ocr_result_path: Optional[str] = None):
    """Import data from Telegram JSON export"""
    # Find and load the result.json file
    result_file = base_dir / 'result.json'
    if not result_file.exists():
        raise FileNotFoundError(f'Could not find result.json in {base_dir}')

    with open(result_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Load optional OCR results file if provided
    ocr_results = {}
    if ocr_result_path:
        with open(ocr_result_path, 'r', encoding='utf-8') as f:
            ocr_result_data = json.load(f)
            ocr_results = {item['name']: item['text'] for item in ocr_result_data}

    # Extract channel info
    channel_id = data.get('id')
    channel_name = data.get('name')

    if not channel_id or not channel_name:
        raise ValueError('Invalid channel data in JSON file')

    # Get or create channel
    channel = await get_or_create_channel(channel_id, channel_name)

    # Process messages
    for message in tqdm(data.get('messages', [])):
        # Skip messages without photos
        if 'photo' not in message:
            continue

        photo_path = str(base_dir / message['photo'])
        if not os.path.exists(photo_path):
            print(f'Warning: Photo {photo_path} does not exist, skipping.')
            continue

        # Get OCR result from provided file or generate using OCR
        photo_name = Path(message['photo']).name
        ocr_text = ocr_results.get(photo_name) if ocr_results else None

        # Process image
        image_phash, text = await process_image(photo_path, ocr_text)

        # Get or create image record
        image = await get_or_create_image(image_phash, text)

        # Link image to channel
        message_id = message.get('id')

        # Check if the link already exists to avoid duplicates
        existing = await fetch_val(
            select(ChannelMessage).where(
                ChannelMessage.channel_id == channel.id,
                ChannelMessage.message_id == message_id,
            )
        )

        if not existing:
            channel_image = ChannelMessage(
                channel_id=channel.id, image_id=image.id, message_id=message_id
            )
            session.add(channel_image)

    print(f'Successfully imported channel {channel_name} (ID: {channel_id})')


async def main():
    parser = argparse.ArgumentParser(description='Import Telegram channel data')
    parser.add_argument(
        'base_dir', help='Path to the directory containing result.json and photos'
    )
    parser.add_argument('--ocr-result', help='Optional path to OCR results JSON file')

    args = parser.parse_args()

    # Ensure necessary directories exist
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    base_dir = Path(args.base_dir)

    async with new_session():
        await import_from_json(base_dir, args.ocr_result)


if __name__ == '__main__':
    asyncio.run(main())

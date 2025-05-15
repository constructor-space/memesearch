import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import easyocr
from sqlalchemy import select
from tqdm import tqdm

from app.db import new_session, session, fetch_val
from app.models.channel import ChannelMessage
from app.config import IMAGES_DIR
from app.utils import get_or_create_channel, process_image, get_or_create_image


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
    channel_username = input('Channel username: ')

    if not channel_id or not channel_name:
        raise ValueError('Invalid channel data in JSON file')

    # Get or create channel
    channel = await get_or_create_channel(channel_id, channel_name, channel_username)

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
        image_phash, text = process_image(photo_path, ocr_text)

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

import os
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from telethon import TelegramClient

from app.bot_client import NewMessage
from app.config import config
from app.config import USERBOT_SESSION_FILE
from app.db import new_session
from app.models import Channel
from app import db
from app.utils import download_to_path, process_media_message


def create_client():
    device_model = None
    if sys.platform == 'linux':
        if os.path.isfile('/sys/devices/virtual/dmi/id/product_name'):
            with open('/sys/devices/virtual/dmi/id/product_name') as f:
                device_model = f.read().strip()
    elif sys.platform == 'darwin':
        device_model = (
            subprocess.check_output('sysctl -n hw.model'.split(' ')).decode().strip()
        )
    elif sys.platform == 'win32':
        device_model = ' '.join(
            subprocess.check_output('wmic computersystem get manufacturer,model')
            .decode()
            .replace('Manufacturer', '')
            .replace('Model', '')
            .split()
        )

    client = TelegramClient(
        str(USERBOT_SESSION_FILE),
        config.api_id,
        config.api_hash,
        device_model=device_model,
        system_version=platform.platform(),
        lang_code='en',
        system_lang_code='en-US',
    )
    client.parse_mode = 'html'
    return client

client = create_client()

OCR_EXECUTOR = ThreadPoolExecutor(max_workers=1)

#listen to new messages
@client.on(NewMessage())
async def on_new_message(event: NewMessage.Event):
    print(f"New message in {event.chat.id}")
    if not event.is_channel or event.message.photo is None:
        return
    async with new_session():
        channel = await db.fetch_val(select(Channel).where(Channel.id == event.chat.id))
        if not channel:
            return
    path, ph = await download_to_path(event.message)
    await process_media_message(path, ph, channel.id, event.message.id, OCR_EXECUTOR)
    #logging
    print(f"Downloaded {event.message.id} from {channel.name} ({channel.username})")
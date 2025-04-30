import os
import platform
import subprocess
import sys

from telethon import TelegramClient
from app.config import config
from app.config import USERBOT_SESSION_FILE

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
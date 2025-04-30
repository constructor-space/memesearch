import asyncio
from app.bot import bot
from app.config import config
from app.userbot_client import client


async def main():
    await bot.start(config.bot_token)
    await client.start()
    await bot.run_until_disconnected()


asyncio.run(main())

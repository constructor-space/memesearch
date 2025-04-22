import asyncio
from app.bot import bot
from app.config import config


async def main():
    await bot.start(config.bot_token)
    await bot.run_until_disconnected()


asyncio.run(main())

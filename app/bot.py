from uuid import uuid4
from sqlalchemy import select
from app import db
from app.bot_client import BotClient, MiddlewareCallback
from app.config import IMAGES_DIR, SESSION_FILE, config
from telethon.events import StopPropagation, InlineQuery
from telethon.events.common import EventCommon

from app.db import new_session
from app.models import Image


async def create_db_session_middleware(
    event: EventCommon, callback: MiddlewareCallback
):
    sp = None
    async with new_session():
        try:
            await callback()
        except StopPropagation as e:
            sp = e
    if sp:
        raise sp


bot = BotClient(str(SESSION_FILE), config.api_id, config.api_hash)
bot.add_middleware(create_db_session_middleware)


def image_to_tg(image: Image):
    if config.debug:
       return IMAGES_DIR / f'{image.phash}.jpg'
    else:
       return config.external_url + f'/{image.phash}.jpg'


@bot.on(InlineQuery())
async def on_inline(e: InlineQuery.Event):
    dist = Image.text.op('<->>')(e.text).label('dist')
    limit = 10
    images = await db.fetch_vals(
        select(Image).where(dist < 0.7).order_by(dist).limit(limit)
    )

    await e.answer(
        [
            e.builder.photo(
                image_to_tg(image),
                id=str(uuid4()),
            )
            for image in images
        ],
        gallery=True,
    )

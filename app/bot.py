import tempfile
from uuid import uuid4
from sqlalchemy import select
from telethon.tl.types import InputMessagesFilterPhotos

from app import db
from app.bot_client import BotClient, MiddlewareCallback, Command
from app.config import IMAGES_DIR, SESSION_FILE, config
from telethon.events import StopPropagation, InlineQuery
from telethon.events.common import EventCommon

from app.db import new_session, session
from app.models import Image, ChannelMessage
from app.scripts.import_tg_channel import process_image, get_or_create_image, get_or_create_channel
from app.userbot_client import client

from sqlalchemy.dialects.postgresql import insert


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
       return IMAGES_DIR / f'{image.sha256}.jpg'
    else:
       return config.external_url + f'/{image.sha256}.jpg'


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

@bot.on(Command('download_channel'))
async def on_start(e: Command.Event):
    if e.message.chat_id != config.admin_group_id:
        return
    channel_name = e.args
    channel_tg = await client.get_entity(channel_name)
    channel = await get_or_create_channel(channel_tg)
    it = client.iter_messages(channel_tg, filter=InputMessagesFilterPhotos)
    mess = await e.message.reply(f'Downloading 0 of {it.total}')
    i = 0
    async for message in it:
        if i % 10 == 0:
            await mess.edit(f'Downloading {i} of {it.total}')
        if not message.photo:
            continue
        with tempfile.NamedTemporaryFile(delete_on_close=False) as fp:
            await message.download_media(fp)
            fp.close()
            image_phash, ocr_text = await process_image(fp.name)
        image = await get_or_create_image(image_phash, ocr_text)
        await db.session.execute(insert(ChannelMessage).values(
            channel_id=channel.id,
            image_id=image.id,
            message_id=message.id,
        ).on_conflict_do_nothing())
        i += 1
    await mess.edit(f'Downloaded {i} of {it.total}')
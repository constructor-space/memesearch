import asyncio
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image as PILImage
from imagehash import phash
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from telethon import Button
from telethon.events import StopPropagation, InlineQuery
from telethon.events.common import EventCommon
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputMessagesFilterPhotos, DocumentAttributeSticker

from app import db
from app.bot_client import BotClient, MiddlewareCallback, NewMessage, Command, Message
from app.config import IMAGES_DIR, SESSION_FILE, config
from app.db import new_session, fetch_vals
from app.models import Image, ChannelMessage
from app.models.sticker import Sticker, StickerSet
from app.userbot_client import client
from app.utils import get_or_create_channel, process_image, get_or_create_image, calculate_phash, save_image


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


@bot.on(Command('start'))
@bot.on(Command('help'))
async def on_start(e: Command.Event):
    await e.message.respond(
        f'Hi! I can help you find memes from Telegram.'
        f'Click on a button below to try or type `@{bot.me.username}` in any chat.'
        f'\n\n'
        f'You can also send me a photo to find channels where it was posted.',
        buttons=[
            [Button.switch_inline('Try in this chat', same_peer=True)],
            [Button.switch_inline('Try in other chat')],
        ],
        parse_mode='markdown',
    )


def image_to_tg(image: Image):
    if config.debug:
        return IMAGES_DIR / f'{image.phash}.jpg'
    else:
        return config.external_url + f'/{image.phash}.jpg'


@bot.on(InlineQuery())
async def on_inline(e: InlineQuery.Event):
    offset = int(e.offset or '0')

    dist = Image.text.op('<->>')(e.text).label('dist')
    limit = 10
    images = await db.fetch_vals(
        select(Image).where(dist < 0.7).order_by(dist).limit(limit).offset(offset)
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
        next_offset=str(offset + limit),
    )


@bot.on(NewMessage(pm_only=True))
async def on_new_message(e: NewMessage.Event):
    if e.message.photo is None:
        await e.reply('Please send me an image for reverse search.')
        return

    photo_save_path = f'/tmp/{e.message.photo.id}.jpg'
    await e.message.download_media(file=photo_save_path, thumb=-1)
    image_phash = str(phash(PILImage.open(photo_save_path)))

    messages = await fetch_vals(
        select(ChannelMessage).join(Image).where(Image.phash == image_phash)
    )
    if messages:
        await e.reply(
            '\n'.join(
                [
                    f't.me/c/{message.channel_id}/{message.message_id}'
                    for message in messages
                ]
            )
        )
        return
    sticker_sets = await fetch_vals(
        select(StickerSet).join(Sticker).join(Image)
    )
    if sticker_sets:
        await e.reply("\n".join([f"t.me/addstickers/{pack.short_name}" for pack in sticker_sets]))
        return
    await e.reply('Image not found.')


@dataclass
class StickerJob:
    file_path: Path
    sticker_pack_id: int


@dataclass
class MessageJob:
    file_path: Path
    channel_id: int
    message_id: int


@bot.on(Command('download_channel'))
async def on_download_channel(e: Command.Event):
    if e.message.chat_id != config.admin_group_id:
        return

    channel_name = e.args
    channel_tg = await client.get_entity(channel_name)
    async with new_session():
        channel = await get_or_create_channel(
            channel_tg.id, channel_tg.title, channel_tg.username
        )

    work_q: asyncio.Queue[StickerJob | MessageJob | None] = asyncio.Queue()
    processed = queued = 0
    last_edited = time.time()
    mess = await e.message.reply('Downloading 0 / Processed 0')

    executor = ThreadPoolExecutor(max_workers=1)

    async def worker():
        nonlocal last_edited
        nonlocal processed
        loop = asyncio.get_running_loop()
        while True:
            item = await work_q.get()
            if item is None:          # сигнал завершения
                work_q.task_done()
                break

            try:
                text = await loop.run_in_executor(executor, process_image, str(path))
                async with new_session():
                    img = await get_or_create_image(ph, text)
                    if isinstance(item, MessageJob):
                        await db.session.execute(
                            insert(ChannelMessage)
                            .values(
                                channel_id=item.channel_id,
                                image_id=img.id,
                                message_id=item.message_id,
                            )
                            .on_conflict_do_nothing()
                        )
                    elif isinstance(item, StickerJob):
                        await db.session.execute(insert(Sticker).values(
                            image_id=img.id,
                            sticker_pack_id=item.sticker_pack_id,
                        ).on_conflict_do_nothing())
                    else:
                        raise TypeError(f'Unknown item type: {type(item)}')
                processed += 1
                if time.time() - last_edited > 10:
                    last_edited = time.time()
                    await mess.edit(f'Downloading {queued} / Processed {processed}')
            except Exception as e:
                print(f'Error processing {path}: {e}')
            finally:
                work_q.task_done()

    worker_task = asyncio.create_task(worker())

    it = client.iter_messages(channel_tg, filter=InputMessagesFilterPhotos)
    async for message in it:
        message: Message
        if message.photo:
            with tempfile.NamedTemporaryFile(delete_on_close=False) as fp:
                await message.download_media(fp)
                fp.close()
                ph = calculate_phash(fp.name)
                path = save_image(fp.name, ph)
            await work_q.put(MessageJob(path, channel.id, message.id))
        elif message.sticker:
            input_sticker_set = next(attr for attr in message.document.attributes if isinstance(attr, DocumentAttributeSticker)).stickerset
            sticker_set = await client(GetStickerSetRequest(input_sticker_set, 0))
            await db.session.execute(insert(StickerSet).values(
                id=sticker_set.set.id,
                short_name=sticker_set.set.short_name,
            ).on_conflict_do_nothing())
            for document in sticker_set.documents:
                with tempfile.NamedTemporaryFile(delete_on_close=False) as fp:
                    await client.download_media(document, fp)
                    fp.close()
                    ph = calculate_phash(fp.name)
                    path = save_image(fp.name, ph)
                await work_q.put(StickerJob(path, sticker_set.set.id))
        else:
            continue
        queued += 1
        if time.time() - last_edited > 10:
            last_edited = time.time()
            await mess.edit(f'Downloading {queued} / Processed {processed}')

    await work_q.join()
    await work_q.put(None)
    await worker_task
    executor.shutdown(wait=True)

    await mess.edit(f'Download finished: {queued} queued, {processed} processed')
import asyncio
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from PIL import Image as PILImage
from imagehash import phash
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from telethon import Button
from telethon.events import StopPropagation, InlineQuery
from telethon.events.common import EventCommon
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputMessagesFilterPhotos

from app import db
from app.bot_client import BotClient, MiddlewareCallback, NewMessage, Command, Message
from app.config import IMAGES_DIR, SESSION_FILE, config
from app.db import new_session, fetch_vals
from app.models import Image, ChannelMessage
from app.models.sticker import Sticker, StickerSet
from app.userbot_client import client
from app.utils import get_or_create_channel, StickerData, MessageData, process_media_message, download_to_path


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


OCR_EXECUTOR = ThreadPoolExecutor(max_workers=1)

@bot.on(Command("download_channel"))
async def on_download_channel(e):
    if e.message.chat_id != config.admin_group_id:
        return

    channel_name = e.args
    channel_tg = await client.get_entity(channel_name)
    async with new_session():
        channel = await get_or_create_channel(channel_tg.id, channel_tg.title, channel_tg.username)

    work_q: asyncio.Queue[StickerData | MessageData | None] = asyncio.Queue()
    processed = queued = 0
    last_edited = time.time()
    mess = await e.message.reply("Downloading 0 / Processed 0")

    async def worker():
        nonlocal processed, last_edited
        while True:
            item = await work_q.get()
            if item is None:
                work_q.task_done()
                break

            try:
                await process_media_message(item, OCR_EXECUTOR)
                processed += 1
                if time.time() - last_edited > 10:
                    last_edited = time.time()
                    await mess.edit(f"Downloading {queued} / Processed {processed}")
            except Exception as exc:
                traceback.print_exc()
                await mess.reply(f"Error processing {item}: {exc}")
            finally:
                work_q.task_done()

    worker_task = asyncio.create_task(worker())

    it = client.iter_messages(channel_tg, filter=InputMessagesFilterPhotos)
    async for message in it:
        message: Message
        if message.photo:
            path, ph = await download_to_path(message)
            await work_q.put(MessageData(path, ph, channel.id, message.id))
        elif message.sticker:
            input_sticker_set = next(attr for attr in message.document.attributes if isinstance(attr, DocumentAttributeSticker)).stickerset
            sticker_set = await client(GetStickerSetRequest(input_sticker_set, 0))
            await db.session.execute(insert(StickerSet).values(
                id=sticker_set.set.id,
                short_name=sticker_set.set.short_name,
            ).on_conflict_do_nothing())
            for document in sticker_set.documents:
                path, ph = await download_to_path(document)
                await work_q.put(StickerData(path, ph, sticker_set.set.id))
        else:
            continue
        queued += 1
        if time.time() - last_edited > 10:
            last_edited = time.time()
            await mess.edit(f"Downloading {queued} / Processed {processed}")

    await work_q.join()
    await work_q.put(None)
    await worker_task

    await mess.edit(f"Download finished: {queued} queued, {processed} processed")

    try:
        await client(JoinChannelRequest(channel_tg))
    except Exception as exc:
        await e.message.reply(f"Error joining channel {channel_name}: {exc}")

if __name__ == "__main__":
    bot.run_until_disconnected()

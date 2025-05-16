import asyncio
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from telethon import Button
from telethon.events import StopPropagation, InlineQuery
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputMessagesFilterPhotos, DocumentAttributeSticker

from app import db
from app.bot_client import BotClient, MiddlewareCallback, Command, Message
from app.config import IMAGES_DIR, SESSION_FILE, config
from app.db import new_session
from app.models import Image
from app.models.sticker import StickerSet
from app.userbot_client import client
from app.utils import (
    get_or_create_channel,
    StickerData,
    MessageData,
    process_media_message,
    download_to_path,
)


async def create_db_session_middleware(
    _event: Any, callback: MiddlewareCallback
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


from sqlalchemy import literal, Float
from pgvector.sqlalchemy import Vector
from app.utils import embed_text                   # ← tiny helper next to embed_image

from sqlalchemy import bindparam, String
from pgvector.sqlalchemy import Vector
from sqlalchemy import select
from uuid import uuid4

@bot.on(InlineQuery())
async def on_inline(e: InlineQuery.Event):
    query = (e.text or "").strip()
    if not query:
        return

    offset = int(e.offset or "0")
    limit  = 10

    # 1) Python-side embed the text
    qvec = embed_text(query)  # -> list[512 floats]

    # 2) bind-params for vector and text
    vec_param = bindparam("qvec", value=qvec, type_=Vector(512))
    txt_param = bindparam("qtxt", value=query, type_=String)

    # 3) distance expressions
    emb_dist = Image.embedding.op("<=>")(vec_param)  # cosine distance
    txt_dist = Image.text.op("<->>")(txt_param)      # trigram distance

    # 4) fuse with SQL literals so they aren’t extra params
    score = (literal(0.65) * emb_dist + literal(0.35) * txt_dist).label("score")

    # 5) build statement
    stmt = (
        select(Image)
        .where(Image.embedding != None)
        .order_by(score)
        .limit(limit)
        .offset(offset)
    )

    # 6) execute, passing only the two bind-params
    images = await db.fetch_vals(stmt, {"qvec": qvec, "qtxt": query})

    # 7) reply
    await e.answer(
        [e.builder.photo(image_to_tg(img), id=str(uuid4())) for img in images],
        gallery=True,
        next_offset=str(offset + limit),
    )


OCR_EXECUTOR = ThreadPoolExecutor(max_workers=1)
EMB_EXECUTOR = ThreadPoolExecutor(max_workers=1)

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
                # передаём оба executors
                await process_media_message(item, OCR_EXECUTOR, EMB_EXECUTOR)
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

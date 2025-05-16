import asyncio
import struct
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from imagehash import phash
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from telethon import Button, events
from telethon.events import StopPropagation, InlineQuery
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import DocumentAttributeSticker, UpdateBotInlineSend, Photo, Document, InputPhoto, InputDocument

from app import db
from app.bot_client import BotClient, MiddlewareCallback, Command, Message, NewMessage
from app.config import IMAGES_DIR, SESSION_FILE, config
from app.db import new_session
from app.models import Image, ChannelMessage
from app.models.image_usage import ImageUsage
from app.models.sticker import StickerSet, Sticker
from app.userbot_client import client
from app.utils import (
    get_or_create_channel,
    StickerData,
    MessageData,
    is_ad_message,
    process_media_message,
    download_to_path,
    embed_text, embed_image,
)
from PIL import Image as PILImage

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


@bot.on(events.Raw([UpdateBotInlineSend]))
async def feedback(event: UpdateBotInlineSend):
    img_id, _ = event.id.split('_', 1)
    if not img_id.isdigit():
        return
    image = await db.fetch_val(
        select(Image).where(Image.id == int(img_id))
    )
    if not image:
        return
    db.session.add(
        ImageUsage(
            image_id=image.id,
            user_id=event.user_id,
        )
    )


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
    if image.tg_ref:
        return unpack_file_ref(image.tg_ref)
    if config.debug:
        return IMAGES_DIR / f'{image.phash}.jpg'
    else:
        return config.external_url + f'/{image.phash}.jpg'


def pack_file_ref(file: InputPhoto | Photo | InputDocument | Document) -> bytes:
    type_ = 1 if isinstance(file, (Photo, InputPhoto)) else 2
    return struct.pack('>Hqq', type_, file.id, file.access_hash) + file.file_reference


def unpack_file_ref(file_ref: bytes) -> InputPhoto | InputDocument:
    type_, id_, access_hash = struct.unpack('>Hqq', file_ref[:2 + 8 + 8])
    file_ref = file_ref[2 + 8 + 8:]
    if type_ == 1:
        return InputPhoto(id_, access_hash, file_ref)
    elif type_ == 2:
        return InputDocument(id_, access_hash, file_ref)


async def respond_with_images(e: InlineQuery.Event, images, offset, limit):
    results = await asyncio.gather(
        *[e.builder.photo(image_to_tg(img), id=f'{img.id}_{uuid4()}') for img in images]
    )
    for i, img in enumerate(images):
        if not img.tg_ref:
            img.tg_ref = pack_file_ref(results[i].photo)
    await e.answer(
        results,
        gallery=True,
        next_offset=str(offset + limit),
    )


async def respond_with_most_used(e: InlineQuery.Event, offset, limit, query):
    usage_count_q = (
        select(
            ImageUsage.image_id.label('image_id'),
            func.count(ImageUsage.id).label('usage_count'),
        )
        .group_by(ImageUsage.image_id)
        .subquery()
    )

    images = await db.fetch_vals(
        select(Image)
        .join(usage_count_q, usage_count_q.c.image_id == Image.id)
        # .where(usage_count_q.c.usage_count > 0)
        .order_by(usage_count_q.c.usage_count.desc())
        .limit(limit)
        .offset(offset)
    )

    return await respond_with_images(e, images, offset, limit)


@bot.on(InlineQuery())
async def on_inline(e: InlineQuery.Event):
    offset = int(e.offset or '0')
    limit = 10
    query = (e.text or '').strip()
    if not query:
        return await respond_with_most_used(e, offset, limit, query)

    qvec = embed_text(query)

    emb_dist = func.greatest(
        sa.cast(Image.embedding.op('<=>')(qvec), sa.Float) - 0.8, 0.0
    ).label('emb_dist')
    txt_dist = Image.text.op('<->>')(query).label('txt_dist')

    dist = sa.case(
        (Image.embedding == None, txt_dist),
        (Image.text == None, emb_dist),
        else_=func.least(emb_dist, txt_dist),
    ).label('dist')

    images = await db.fetch_vals(
        select(Image).where(dist < 0.7).order_by(dist).limit(limit).offset(offset)
    )

    if not images:
        if offset == 0:
            await e.answer(switch_pm='No results found', switch_pm_param='no_results')
        else:
            # scrolled to the end
            await e.answer(None)
        return

    await respond_with_images(e, images, offset, limit)


@bot.on(NewMessage(pm_only=True))
async def on_new_message(e: NewMessage.Event):
    if e.message.photo is None:
        await e.reply('Please send me an image for reverse search.')
        return

    photo_save_path = f'/tmp/{e.message.photo.id}.jpg'
    await e.message.download_media(file=photo_save_path, thumb=-1)
    image_phash = str(phash(PILImage.open(photo_save_path)))

    messages = await db.fetch_vals(
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
    sticker_sets = await db.fetch_vals(
        select(StickerSet).join(Sticker).join(Image)
    )
    if sticker_sets:
        await e.reply("\n".join([f"t.me/addstickers/{pack.short_name}" for pack in sticker_sets]))
        return
    await e.reply('Image not found.')


OCR_EXECUTOR = ThreadPoolExecutor(max_workers=1)
EMB_EXECUTOR = ThreadPoolExecutor(max_workers=1)

@bot.on(Command("update_embedding"))
async def on_update_embedding(e):
    #looks into database, if vector embedding is None or empty, update it
    if e.message.chat_id != config.admin_group_id:
        return

    mess = await e.message.reply("Processed 0")
    last_edited = time.time()
    updated = 0
    images = await db.fetch_vals(
        select(Image).where(Image.embedding == None)
    )
    if not images:
        await e.message.reply("No images to update")
        return
    for img in images:
        try:
            vec = embed_image(str(IMAGES_DIR / f"{img.phash}.jpg"))
            async with new_session():
                await db.session.execute(update(Image).where(Image.id == img.id).values(embedding=vec))
            updated += 1
            if time.time() - last_edited > 10:
                last_edited = time.time()
                await mess.edit(f"Processed {updated} out of {len(images)}")
        except Exception as exc:
            await e.message.reply(f"Error processing {img}: {exc}")
            traceback.print_exc()
    await mess.edit(f"Updated {updated} out of {len(images)}")


@bot.on(Command("download_channel"))
async def on_download_channel(e):
    if e.message.chat_id != config.admin_group_id:
        return

    channel_name = e.args
    #if "!vector" contains in message args, set run_ocr to False, delete it from args
    run_vector = True
    run_ocr = True
    if "!vector" in channel_name:
        run_ocr = False
        channel_name = channel_name.replace("!vector", "").strip()
    if "!text" in channel_name:
        run_vector = False
        channel_name = channel_name.replace("!text", "").strip()

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
                await process_media_message(item, OCR_EXECUTOR, EMB_EXECUTOR, run_ocr, run_vector)
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

    it = client.iter_messages(channel_tg)
    async for message in it:
        message: Message
        if is_ad_message(message):
            continue
        if message.photo:
            path, ph = await download_to_path(message)
            await work_q.put(MessageData(path, ph, channel.id, message.id))
        elif message.sticker:
            input_sticker_set = next(attr for attr in message.document.attributes if isinstance(attr, DocumentAttributeSticker)).stickerset
            sticker_set = await client(GetStickerSetRequest(input_sticker_set, 0))
            async with new_session():
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

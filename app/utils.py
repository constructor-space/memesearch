import asyncio
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Counter, Optional, Union

import cv2
import easyocr
import torch
import open_clip
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from PIL import Image as PILImage
from imagehash import phash
from telethon.tl.types import MessageEntityTextUrl

from app import db
from app.bot_client import Message
from app.db import session, fetch_val, new_session
from app.models import Channel, Image, ChannelMessage, Sticker
from app.config import IMAGES_DIR

# ── OCR ──────────────────────────────────────────────────────────────────────
eocr = easyocr.Reader(["ru", "en"])

def _pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

_DEVICE    = _pick_device()
_PRECISION = "fp16" if _DEVICE.type == "cuda" else "fp32"

# ←── simply swap in the SigLIP2‐384 model name OpenCLIP knows
_MODEL, _PREP = open_clip.create_model_from_pretrained(
    'hf-hub:timm/ViT-SO400M-16-SigLIP2-384',
    precision=_PRECISION,
)
_MODEL.eval().to(_DEVICE)
tokenizer = open_clip.get_tokenizer('hf-hub:timm/ViT-SO400M-16-SigLIP2-384')
print(tokenizer)

@torch.no_grad()
def embed_image(path: str) -> list[float]:
    img = _PREP(PILImage.open(path)).unsqueeze(0).to(_DEVICE)
    if _DEVICE.type == "cuda":
        with torch.cuda.amp.autocast():
            vec = _MODEL.encode_image(img)
    else:
        vec = _MODEL.encode_image(img)
    return vec.squeeze().cpu().tolist()  # 512-d vector

@torch.no_grad()
def embed_text(text: str) -> list[float]:
    """
    Encode a piece of text into the same 512-d vector space as images.
    Returns a Python list of floats.
    """
    # tokenize returns a Tensor of shape [1, seq_len]
    tokens = tokenizer([text], context_length=_MODEL.context_length).to(_DEVICE)

    # on CUDA use AMP for fp16, otherwise plain
    if _DEVICE.type == "cuda":
        with torch.cuda.amp.autocast():
            vec = _MODEL.encode_text(tokens)
    else:
        vec = _MODEL.encode_text(tokens)

    return vec.squeeze().cpu().tolist()

# ─────────────────────────────────────────────────────────────────────────────
# download
# ─────────────────────────────────────────────────────────────────────────────
async def download_to_path(media) -> tuple[Path, str]:
    from app.userbot_client import client
    with tempfile.NamedTemporaryFile(delete_on_close=False) as fp:
        await client.download_media(media, fp)
        fp.close()
        ph = calculate_phash(fp.name)
        return save_image(fp.name, ph), ph

# ─────────────────────────────────────────────────────────────────────────────
# dataclasses
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StickerData:
    file_path: Path
    phash: str
    sticker_pack_id: int

@dataclass
class MessageData:
    file_path: Path
    phash: str
    channel_id: int
    message_id: int

# ─────────────────────────────────────────────────────────────────────────────
# main processor
# ─────────────────────────────────────────────────────────────────────────────
async def process_media_message(
    data: Union[StickerData, MessageData],
    OCR_EXECUTOR,
    EMB_EXECUTOR,
    run_ocr: bool = True, run_vector: bool = True,
):
    loop = asyncio.get_running_loop()

    # OCR text (CPU)
    text = None
    if run_ocr:
        text = await loop.run_in_executor(OCR_EXECUTOR, process_image, str(data.file_path))


    vec = None
    if run_vector:
        vec = await loop.run_in_executor(EMB_EXECUTOR, embed_image, str(data.file_path))

    async with new_session():
        img = await get_or_create_image(data.phash, text, vec)

        if isinstance(data, MessageData):
            await db.session.execute(
                insert(ChannelMessage)
                .values(
                    channel_id=data.channel_id,
                    image_id=img.id,
                    message_id=data.message_id,
                )
                .on_conflict_do_nothing()
            )
        elif isinstance(data, StickerData):
            await db.session.execute(
                insert(Sticker)
                .values(image_id=img.id, sticker_pack_id=data.sticker_pack_id)
                .on_conflict_do_nothing()
            )
        else:
            raise TypeError(f"Unknown item type: {type(data)}")

# ─────────────────────────────────────────────────────────────────────────────
# misc helpers (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
async def get_or_create_channel(id_: int, title: str, username: str) -> Channel:
    channel = await Channel.get(id_)
    if not channel:
        channel = Channel(id=id_, name=title, username=username)
        session.add(channel)
        await session.flush()
    return channel

def calculate_phash(image_path: str) -> str:
    return str(phash(PILImage.open(image_path)))

def save_image(image_path: str, phash: str) -> Path:
    """Save image to the IMAGES_DIR with its phash as filename"""
    target_path = IMAGES_DIR / f'{phash}.jpg'
    if not target_path.exists():
        shutil.copy(image_path, target_path)
    return target_path

def process_image(
    photo_path: str, ocr_result: Optional[str] = None
) -> str:
    """Process an image file and return its hash and text content"""
    # Ensure images directory exists
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # If ocr_result is provided, use it
    if ocr_result:
        return ocr_result

    # Convert image for OCR
    image_cv2 = cv2.cvtColor(cv2.imread(photo_path), cv2.COLOR_BGR2RGB)

    # Run OCR
    ocr_result = eocr.readtext(image_cv2)
    ocr_text = '\n'.join([item[1] for item in ocr_result])

    return ocr_text


async def get_or_create_image(image_phash: str, text: str | None, embedding: list[float] | None) -> Image:
    image = await fetch_val(select(Image).where(Image.phash == image_phash))
    if not image:
        image = Image(phash=image_phash, text=text, embedding=embedding)
        session.add(image)
        await session.flush()
    if image.embedding is None and embedding:
        image.embedding = embedding
        await session.flush()
    if not image.text and text:
        image.text = text
        await session.flush()
    return image


def is_ad_message(message: Message) -> bool:
    links = Counter(x.url for x in (message.entities or []) if isinstance(x, MessageEntityTextUrl))
    top_link_count = links.most_common(1)[0][1] if links else 0
    return top_link_count >= 2

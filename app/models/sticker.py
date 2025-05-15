from app.models.base import Base
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

class Sticker(Base):
    __tablename__ = 'sticker'
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey('image.id'), unique=True)
    sticker_pack_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey('sticker_set.id'), unique=True
    )

class StickerSet(Base):
    __tablename__ = 'sticker_set'
    id: Mapped[int] = mapped_column(primary_key=True)
    short_name: Mapped[str]

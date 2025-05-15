from app.models.base import Base
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

class Sticker(Base):
    __tablename__ = 'sticker'
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey('image.id'), unique=True)
    sticker_pack_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey('sticker_pack.id'), unique=True
    )

class StickerPack(Base):
    __tablename__ = 'sticker_pack'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

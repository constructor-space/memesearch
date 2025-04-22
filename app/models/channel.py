from app.models.base import Base
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


class Channel(Base):
    __tablename__ = 'channel'
    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    name: Mapped[str]


class ChannelMessage(Base):
    __tablename__ = 'channel_message'
    channel_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey('channel.id'), primary_key=True
    )
    message_id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(sa.ForeignKey('image.id'))


__all__ = ['Channel', 'ChannelMessage']

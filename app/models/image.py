from typing import Optional
from pgvector.sqlalchemy import Vector   # new import

from app.models.base import Base
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


class Image(Base):
    __tablename__ = 'image'
    id: Mapped[int] = mapped_column(primary_key=True)
    phash: Mapped[str] = mapped_column(unique=True)
    tg_ref: Mapped[bytes | None]
    text: Mapped[str | None]
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1152))
    __table_args__ = (
        sa.Index(
            'ix_search_data_text',
            'text',
            postgresql_using='gist',
            postgresql_ops={
                'text': 'gist_trgm_ops',
            },
        ),
    )


__all__ = ['Image']

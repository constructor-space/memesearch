from typing import Optional
from pgvector.sqlalchemy import Vector   # new import

from app.models.base import Base
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


class Image(Base):
    __tablename__ = 'image'
    id: Mapped[int] = mapped_column(primary_key=True)
    phash: Mapped[str] = mapped_column(unique=True)
    text: Mapped[str]
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(512))
    __table_args__ = (
        sa.Index(
            'ix_search_data_text',
            sa.text("(text || coalesce(keywords, '')) gist_trgm_ops"),
            postgresql_using='gist',
        ),
    )


__all__ = ['Image']

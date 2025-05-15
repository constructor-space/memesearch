from typing import Optional

from app.models.base import Base
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


class Image(Base):
    __tablename__ = 'image'
    id: Mapped[int] = mapped_column(primary_key=True)
    phash: Mapped[str] = mapped_column(unique=True)
    keywords: Mapped[Optional[str]]
    text: Mapped[str]
    __table_args__ = (
        sa.Index(
            'ix_search_data_text',
            sa.text("(text || coalesce(keywords, '')) gist_trgm_ops"),
            postgresql_using='gist',
        ),
    )


__all__ = ['Image']

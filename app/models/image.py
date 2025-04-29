from app.models.base import Base
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


class Image(Base):
    __tablename__ = 'image'
    id: Mapped[int] = mapped_column(primary_key=True)
    phash: Mapped[str] = mapped_column(unique=True)
    text: Mapped[str]
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

from app.models.base import Base
import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column


class ImageUsage(Base):
    """
    Stores information about images sent by users via inline mode
    """
    __tablename__ = 'image_usage'
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(sa.ForeignKey('image.id'))
    user_id: Mapped[int]
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ['ImageUsage']

from typing import Literal, Type

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def get_models(
    index_type: Literal['gin', 'gist']
) -> (Type[DeclarativeBase], Type[DeclarativeBase]):
    class Base(DeclarativeBase):
        pass

    class Data(Base):
        __tablename__ = 'data'
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]
        text: Mapped[str]
        __table_args__ = (
            sa.Index(
                'ix_search_data_text',
                'text',
                postgresql_using=index_type,
                postgresql_ops={
                    'text': f'{index_type}_trgm_ops',
                },
            ),
        )

    return Base, Data

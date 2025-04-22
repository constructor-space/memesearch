from sqlalchemy.orm.interfaces import ORMOption
from typing import TypeVar, Type, Sequence

from sqlalchemy.orm import DeclarativeBase

from app import db

T = TypeVar('T', bound='Base')


class Base(DeclarativeBase):
    @classmethod
    async def get(
        cls: Type[T],
        pkey: int | tuple[int, ...],
        *,
        options: Sequence[ORMOption] | None = None
    ) -> T | None:
        return await db.session.get(cls, pkey, options=options)

    async def delete(self):
        await db.session.delete(self)

    def dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns.values()}


__all__ = ['Base']

import json
from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import config

engine = create_async_engine(
    config.db_url,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
)
_async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

_session_ctx: ContextVar[AsyncSession] = ContextVar('session')


class _AsyncSessionWrapper:
    def __getattr__(self, item):
        return getattr(_session_ctx.get(), item)


session: AsyncSession = _AsyncSessionWrapper()


@asynccontextmanager
async def new_session():
    async with _async_session() as request_session:
        token = _session_ctx.set(request_session)
        async with request_session.begin():
            yield
        _session_ctx.reset(token)


async def fetch_val(expr, values: dict = None):
    res = await session.execute(expr, values)
    return res.scalars().first()


async def fetch_vals(expr, values: dict = None, unique: bool = False):
    res = await session.execute(expr, values)
    if unique:
        res = res.unique()
    return res.scalars().all()


async def fetch_one(expr, values: dict = None):
    res = await session.execute(expr, values)
    return res.fetchone()


async def fetch_all(expr, values: dict = None):
    res = await session.execute(expr, values)
    return res.fetchall()


__all__ = [
    'engine',
    'new_session',
    'session',
    'db_session_middleware',
    'fetch_val',
    'fetch_vals',
    'fetch_one',
    'fetch_all',
]

"""
数据库连接管理器

用法：
    from shared.database import get_engine, get_session

    engine = get_engine(database_url)
    async with get_session(engine) as session:
        result = await session.execute(...)
"""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def get_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """创建异步数据库引擎"""
    url = database_url or os.environ["DATABASE_URL"]
    return create_async_engine(
        url,
        pool_size=10,
        max_overflow=5,
        pool_timeout=30,
        pool_recycle=1800,
        echo=False,
    )


def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建 Session 工厂"""
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """获取一个数据库 session（上下文管理器）"""
    factory = get_session_factory(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
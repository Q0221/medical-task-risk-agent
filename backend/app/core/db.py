"""异步数据库连接：SQLAlchemy 2.0 + asyncmy。"""

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：提供一个异步数据库会话，自动关闭。"""
    async with AsyncSessionLocal() as session:
        yield session

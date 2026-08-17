from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Creates every table from app.models if it doesn't already exist yet.

    This replaces needing to run `alembic upgrade head` by hand -- useful when you have
    no shell access (e.g. Render's free tier has no Shell tab, mobile-only workflows).
    It is safe to call on every startup: create_all() is a no-op for tables that already
    exist. Alembic migration files are still included in the repo for later, once you
    have terminal access and want proper schema-change tracking.
    """
    from app import models  # noqa: F401  ensure all models are registered on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def session_scope() -> AsyncSession:
    """Use outside of FastAPI dependency injection, e.g. inside the Telegram bot."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

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
    """Creates every table from app.models if it doesn't already exist yet, then applies
    a small set of additive, idempotent ALTER TABLE statements for columns added after the
    table already existed in production (create_all() only creates missing *tables*, it never
    alters existing ones). This keeps the mobile-only / no-shell-access deploy workflow working
    without needing `alembic upgrade head`.
    """
    from app import models  # noqa: F401  ensure all models are registered on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text
        for stmt in (
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS telegram_message_id BIGINT",
        ):
            await conn.execute(text(stmt))


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

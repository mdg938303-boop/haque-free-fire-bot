"""
Single process, single Render Web Service:

  - FastAPI here only exists to satisfy Render's free-tier requirement that a Web
    Service binds to $PORT and answers HTTP requests (used for health checks / uptime
    pings). It has no admin routes -- the Admin Panel lives entirely inside the
    Telegram bot (see app/bot/handlers/admin.py).
  - The Telegram bot (long polling) and the order-status poller both run as background
    asyncio tasks started in the FastAPI lifespan, so `uvicorn app.main:app` is the
    only command you need to run in production.

Local development can still run the bot standalone with `python run_bot.py` if you
don't want the HTTP server at all.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.core.logging import setup_logging
from app.bot.bot import build_dispatcher, _order_status_poll_loop
from app.services.settings_service import ensure_defaults
from app.database import session_scope, init_db

settings = get_settings()
setup_logging(settings.APP_ENV)
logger = logging.getLogger("main")

_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    logger.info("Creating database tables if they don't exist yet...")
    await init_db()

    async with session_scope() as db:
        await ensure_defaults(db)

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Starting Telegram bot polling + order status poller as background tasks...")
    bot_task = asyncio.create_task(dp.start_polling(bot))
    poll_task = asyncio.create_task(_order_status_poll_loop(bot))
    _background_tasks.extend([bot_task, poll_task])

    yield

    for task in _background_tasks:
        task.cancel()
    await bot.session.close()


app = FastAPI(title=settings.APP_NAME, docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running. Admin Panel is inside Telegram -- send /admin to the bot."}

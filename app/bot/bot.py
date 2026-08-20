import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import get_settings
from app.core.logging import setup_logging
from app.bot.handlers import (
    admin, admin_promo, admin_support, admin_reseller, start, uid_check, purchase, wallet, deposit, orders,
    loyalty, support, bulk_purchase, reseller_onboarding,
)
from app.services.order_polling_service import poll_open_orders
from app.services.broadcast_service import dispatch_due as dispatch_due_broadcasts
from app.services.settings_service import ensure_defaults
from app.database import session_scope, init_db

logger = logging.getLogger("bot")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # admin router MUST be included first: its AdminFilter only matches configured
    # TELEGRAM_ADMIN_IDS, so non-admin users simply fall through to the routers below.
    dp.include_router(admin.router)
    dp.include_router(admin_promo.router)
    dp.include_router(admin_support.router)
    dp.include_router(admin_reseller.router)
    dp.include_router(start.router)
    dp.include_router(reseller_onboarding.router)
    dp.include_router(uid_check.router)
    dp.include_router(purchase.router)
    dp.include_router(bulk_purchase.router)
    dp.include_router(wallet.router)
    dp.include_router(deposit.router)
    dp.include_router(orders.router)
    dp.include_router(loyalty.router)
    dp.include_router(support.router)
    return dp


async def _order_status_poll_loop(bot: "Bot") -> None:
    settings = get_settings()
    while True:
        try:
            await poll_open_orders(bot)
        except Exception:  # noqa: BLE001 - one bad poll cycle must never kill the loop
            logger.exception("Order status poll cycle failed")
        await asyncio.sleep(settings.ORDER_POLL_INTERVAL_SECONDS)


async def _broadcast_dispatch_loop(bot: "Bot") -> None:
    while True:
        try:
            await dispatch_due_broadcasts(bot)
        except Exception:  # noqa: BLE001 - one bad cycle must never kill the loop
            logger.exception("Scheduled broadcast dispatch cycle failed")
        await asyncio.sleep(30)


async def run_polling() -> None:
    settings = get_settings()
    setup_logging(settings.APP_ENV)

    await init_db()
    async with session_scope() as db:
        await ensure_defaults(db)

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    logger.info("Starting Telegram bot polling + order status poller...")
    await bot.delete_webhook(drop_pending_updates=True)

    poll_task = asyncio.create_task(_order_status_poll_loop(bot))
    broadcast_task = asyncio.create_task(_broadcast_dispatch_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        poll_task.cancel()
        broadcast_task.cancel()


if __name__ == "__main__":
    asyncio.run(run_polling())

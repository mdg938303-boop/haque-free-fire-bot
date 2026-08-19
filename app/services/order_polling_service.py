"""
Polling replaces webhooks for order status updates (chosen because it needs no public
HTTP endpoint from the provider's side -- works fine on a single Render free web service
that's only exposing a /health route).

`poll_open_orders` is called on a fixed interval (settings.ORDER_POLL_INTERVAL_SECONDS)
from the background task started in app/main.py. It is safe to call concurrently with
normal user-driven order creation because apply_status_update() is idempotent.
"""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from app.database import session_scope
from app.models import Order, OrderStatus, ApiProvider
from app.providers.registry import get_adapter
from app.services import order_service, review_service
from app.bot.keyboards import rating_kb, order_cancel_kb

logger = logging.getLogger("order_poller")

OPEN_STATUSES = (OrderStatus.PENDING, OrderStatus.PROCESSING)


async def poll_open_orders(bot: Bot | None = None) -> None:
    async with session_scope() as db:
        orders = (await db.execute(
            select(Order).where(Order.status.in_(OPEN_STATUSES), Order.provider_order_id.isnot(None))
        )).scalars().all()

        if not orders:
            return

        # Group by provider to reuse one adapter instance per provider per poll cycle.
        provider_cache: dict[str, tuple[ApiProvider, object]] = {}

        for order in orders:
            try:
                provider_key = str(order.provider_id)
                if provider_key not in provider_cache:
                    provider = await db.get(ApiProvider, order.provider_id)
                    if provider is None or not provider.is_active:
                        continue
                    provider_cache[provider_key] = (provider, get_adapter(provider))
                provider, adapter = provider_cache[provider_key]

                result = await adapter.get_order_status(order.provider_order_id)
                try:
                    new_status = OrderStatus(result.status)
                except ValueError:
                    new_status = OrderStatus.PROCESSING

                status_changed = new_status != order.status
                await order_service.apply_status_update(db, order=order, new_status=new_status, raw=result.raw_response)

                needs_review = await review_service.needs_review_prompt(order)
                if needs_review:
                    await review_service.mark_review_prompted(db, order=order)

                if status_changed and bot is not None and order.telegram_chat_id and order.telegram_message_id:
                    is_cancelable = await order_service.is_order_cancelable(db, order)
                    new_markup = order_cancel_kb(order.id) if is_cancelable else None
                    try:
                        await bot.edit_message_text(
                            chat_id=order.telegram_chat_id, message_id=order.telegram_message_id,
                            text=order_service.format_order_card(order), reply_markup=new_markup,
                        )
                    except TelegramBadRequest:
                        pass  # message deleted / not modified / too old to edit -- non-fatal

                    if needs_review:
                        try:
                            await bot.send_message(
                                order.telegram_chat_id,
                                "✅ অর্ডার সম্পন্ন হয়েছে! কেমন লাগলো, রেটিং দিন:",
                                reply_markup=rating_kb(order.id),
                            )
                        except TelegramBadRequest:
                            pass
            except Exception as exc:  # noqa: BLE001 - one bad order must not stop the whole poll cycle
                logger.error("Poll failed for order %s: %s", order.order_number, exc)
                continue

"""
Immediate broadcasts run in a background asyncio task the instant an admin sends the
message (see admin.py). Scheduled broadcasts are persisted to the DB instead, because the
Render free-tier process can restart between "admin schedules it" and "send time arrives" --
an in-memory asyncio.sleep()-based timer would be lost on restart. A periodic background
loop (see bot.py's _broadcast_dispatch_loop, mirroring the order-status poller) picks up
anything whose scheduled_at has passed and is still PENDING.
"""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import session_scope
from app.models import User, Wallet, ScheduledBroadcast

logger = logging.getLogger("broadcast")


async def resolve_target_users(db: AsyncSession, *, target: str) -> list[User]:
    stmt = select(User).where(User.is_banned == False)  # noqa: E712
    if target == "depositors":
        stmt = stmt.join(Wallet).where(Wallet.total_deposit > 0)
    elif target == "buyers":
        stmt = stmt.join(Wallet).where(Wallet.total_purchase > 0)
    return (await db.execute(stmt)).scalars().all()


async def send_broadcast(bot: Bot, *, target: str, text: str) -> tuple[int, int]:
    async with session_scope() as db:
        users = await resolve_target_users(db, target=target)

    sent, failed = 0, 0
    for user in users:
        try:
            await bot.send_message(chat_id=user.telegram_id, text=text)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            failed += 1
        except Exception:  # noqa: BLE001
            failed += 1
        await asyncio.sleep(0.04)  # ~25 msg/sec, safely under Telegram's global rate limit

    return sent, failed


async def run_immediate_broadcast(bot: Bot, *, target: str, text: str, notify_admin_id: int) -> None:
    sent, failed = await send_broadcast(bot, target=target, text=text)
    try:
        await bot.send_message(chat_id=notify_admin_id, text=f"✅ Broadcast সম্পন্ন।\nSent: {sent}\nFailed: {failed}")
    except Exception:  # noqa: BLE001
        pass


# ================================================================ SCHEDULED
async def create_scheduled(
    db: AsyncSession, *, target: str, message: str, scheduled_at: datetime, admin_telegram_id: int,
) -> ScheduledBroadcast:
    row = ScheduledBroadcast(
        target=target, message=message, scheduled_at=scheduled_at,
        status="PENDING", created_by_admin_telegram_id=admin_telegram_id,
    )
    db.add(row)
    await db.flush()
    return row


async def list_pending(db: AsyncSession) -> list[ScheduledBroadcast]:
    return (await db.execute(
        select(ScheduledBroadcast).where(ScheduledBroadcast.status == "PENDING").order_by(ScheduledBroadcast.scheduled_at.asc())
    )).scalars().all()


async def cancel_scheduled(db: AsyncSession, *, broadcast_id: UUID) -> ScheduledBroadcast:
    row = await db.get(ScheduledBroadcast, broadcast_id)
    row.status = "CANCELED"
    await db.flush()
    return row


async def dispatch_due(bot: Bot) -> None:
    """Called every ~30s from the background loop. Marks a row SENT *before* actually
    sending so a crash mid-send can't cause the same broadcast to fire twice on restart."""
    async with session_scope() as db:
        due = (await db.execute(
            select(ScheduledBroadcast).where(
                ScheduledBroadcast.status == "PENDING", ScheduledBroadcast.scheduled_at <= datetime.now(timezone.utc),
            )
        )).scalars().all()
        due_ids = [row.id for row in due]
        for row in due:
            row.status = "SENT"  # optimistic lock -- see docstring
            row.sent_at = datetime.now(timezone.utc)

    for broadcast_id in due_ids:
        async with session_scope() as db:
            row = await db.get(ScheduledBroadcast, broadcast_id)
            target, text, admin_id = row.target, row.message, row.created_by_admin_telegram_id

        try:
            sent, failed = await send_broadcast(bot, target=target, text=text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Scheduled broadcast %s failed: %s", broadcast_id, exc)
            sent, failed = 0, 0

        async with session_scope() as db:
            row = await db.get(ScheduledBroadcast, broadcast_id)
            row.sent_count, row.failed_count = sent, failed

        try:
            await bot.send_message(
                chat_id=admin_id, text=f"✅ শিডিউল করা Broadcast পাঠানো হয়েছে।\nSent: {sent}\nFailed: {failed}",
            )
        except Exception:  # noqa: BLE001
            pass

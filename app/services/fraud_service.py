"""
Lightweight, rule-based fraud signal -- not a full risk engine. The only rule right now:
if a user's deposits get REJECTED by an admin too many times within a rolling window
(likely fake/duplicate transaction-ID claims), auto-flag the account so it's visible at a
glance in the admin Users view. Flagging never blocks the user automatically -- an admin
still decides whether to ban, it's purely a "look closer at this one" signal.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Deposit, DepositStatus
from app.services.settings_service import get_setting


async def check_deposit_fraud(db: AsyncSession, *, user_id: UUID) -> bool:
    """Call this right after a deposit is rejected. Returns True if the user was
    newly flagged by this call (so the caller can notify admins), False otherwise
    (already flagged, or still under the threshold)."""
    user = await db.get(User, user_id)
    if user is None or user.is_flagged:
        return False

    cfg = await get_setting(db, "fraud")
    threshold = int(cfg.get("rejected_deposit_threshold", 3))
    window_hours = int(cfg.get("rejected_deposit_window_hours", 24))
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    count = (await db.execute(
        select(func.count()).select_from(Deposit).where(
            Deposit.user_id == user_id, Deposit.status == DepositStatus.REJECTED, Deposit.reviewed_at >= since,
        )
    )).scalar_one()

    if count < threshold:
        return False

    user.is_flagged = True
    user.flag_reason = f"{window_hours} ঘণ্টায় {count}টি ডিপোজিট রিজেক্ট হয়েছে"
    user.flagged_at = datetime.now(timezone.utc)
    await db.flush()
    return True


async def unflag_user(db: AsyncSession, *, user_id: UUID) -> None:
    user = await db.get(User, user_id)
    if user is not None:
        user.is_flagged = False
        user.flag_reason = None
        await db.flush()


async def list_flagged_users(db: AsyncSession, limit: int = 20) -> list[User]:
    return (await db.execute(
        select(User).where(User.is_flagged == True).order_by(User.flagged_at.desc()).limit(limit)  # noqa: E712
    )).scalars().all()

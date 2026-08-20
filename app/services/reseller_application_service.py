from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResellerApplication
from app.core.exceptions import AppError


async def create_application(db: AsyncSession, *, user_id: UUID, telegram_id: int, message: str | None) -> ResellerApplication:
    existing = (await db.execute(
        select(ResellerApplication).where(ResellerApplication.user_id == user_id, ResellerApplication.status == "PENDING")
    )).scalar_one_or_none()
    if existing is not None:
        raise AppError(internal_detail="duplicate pending application", user_message="⚠️ আপনার একটি আবেদন ইতিমধ্যে পর্যালোচনাধীন আছে।")

    app_row = ResellerApplication(user_id=user_id, telegram_id=telegram_id, message=message, status="PENDING")
    db.add(app_row)
    await db.flush()
    return app_row


async def list_pending(db: AsyncSession) -> list[ResellerApplication]:
    return (await db.execute(
        select(ResellerApplication).where(ResellerApplication.status == "PENDING").order_by(ResellerApplication.created_at.asc())
    )).scalars().all()


async def mark_approved(db: AsyncSession, *, application_id: UUID, admin_telegram_id: int) -> ResellerApplication:
    app_row = await db.get(ResellerApplication, application_id)
    app_row.status = "APPROVED"
    app_row.reviewed_at = datetime.now(timezone.utc)
    app_row.reviewed_by_admin_telegram_id = admin_telegram_id
    await db.flush()
    return app_row


async def mark_rejected(db: AsyncSession, *, application_id: UUID, admin_telegram_id: int) -> ResellerApplication:
    app_row = await db.get(ResellerApplication, application_id)
    app_row.status = "REJECTED"
    app_row.reviewed_at = datetime.now(timezone.utc)
    app_row.reviewed_by_admin_telegram_id = admin_telegram_id
    await db.flush()
    return app_row

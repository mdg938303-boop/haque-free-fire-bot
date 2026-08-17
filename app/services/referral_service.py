from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Referral, TransactionType, User
from app.services import wallet_service
from app.services.settings_service import get_setting


async def get_referral_settings(db: AsyncSession) -> dict:
    return await get_setting(db, "referral")


async def attribute_signup(db: AsyncSession, *, new_user: User, referral_code: str | None) -> None:
    if not referral_code:
        return
    referrer = (await db.execute(select(User).where(User.referral_code == referral_code))).scalar_one_or_none()
    if referrer is None or referrer.id == new_user.id:
        return
    new_user.referred_by_id = referrer.id
    db.add(Referral(referrer_id=referrer.id, referred_user_id=new_user.id))
    await db.flush()


async def maybe_pay_referral_bonus(db: AsyncSession, *, user_id: UUID, deposit_amount: Decimal) -> None:
    settings = await get_referral_settings(db)
    if not settings.get("enabled"):
        return

    min_deposit = Decimal(str(settings.get("min_deposit", "0")))
    bonus_amount = Decimal(str(settings.get("bonus_amount", "0")))
    if deposit_amount < min_deposit or bonus_amount <= 0:
        return

    referral = (await db.execute(
        select(Referral).where(Referral.referred_user_id == user_id, Referral.bonus_paid == False)  # noqa: E712
    )).scalar_one_or_none()
    if referral is None:
        return

    await wallet_service.credit_wallet(
        db,
        user_id=referral.referrer_id,
        amount=bonus_amount,
        txn_type=TransactionType.REFERRAL_BONUS,
        reference_type="referral",
        reference_id=str(referral.id),
        note="Referral bonus for referred user's first qualifying deposit",
    )
    referral.bonus_amount = bonus_amount
    referral.bonus_paid = True
    await db.flush()

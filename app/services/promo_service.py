"""
Promo codes give an optional, user-entered extra discount at checkout (stacked on top of
any automatic VIP discount -- see vip_service.py). A promo code's usage is counted at the
moment an order is *created* for it (not only on final success) -- same convention as
Order.attempt_count -- to prevent someone from farming a limited code by repeatedly
cancelling. If the order later fails, the wallet is refunded as normal but the promo
usage slot is not returned; admins should size max_uses / max_uses_per_user accordingly.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PromoCode, PromoCodeUsage, Order
from app.core.exceptions import (
    PromoCodeInvalidError, PromoCodeExhaustedError, PromoCodeAlreadyUsedError, PromoCodeMinOrderError,
)


async def create_promo(
    db: AsyncSession, *, admin_telegram_id: int, code: str, discount_type: str, discount_value: Decimal,
    max_uses: int | None, max_uses_per_user: int, min_order_amount: Decimal | None, valid_days: int | None,
) -> PromoCode:
    valid_until = (datetime.now(timezone.utc) + timedelta(days=valid_days)) if valid_days else None
    promo = PromoCode(
        code=code.strip().upper(), discount_type=discount_type, discount_value=discount_value,
        max_uses=max_uses, max_uses_per_user=max_uses_per_user, min_order_amount=min_order_amount,
        valid_until=valid_until, is_active=True, created_by_admin_telegram_id=admin_telegram_id,
    )
    db.add(promo)
    await db.flush()
    return promo


async def list_promos(db: AsyncSession) -> list[PromoCode]:
    return (await db.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))).scalars().all()


async def toggle_promo(db: AsyncSession, *, promo_id: UUID) -> PromoCode:
    promo = await db.get(PromoCode, promo_id)
    promo.is_active = not promo.is_active
    await db.flush()
    return promo


async def delete_promo(db: AsyncSession, *, promo_id: UUID) -> str:
    promo = await db.get(PromoCode, promo_id)
    code = promo.code
    await db.delete(promo)
    await db.flush()
    return code


async def validate_and_price(
    db: AsyncSession, *, code: str, user_id: UUID, order_amount: Decimal,
) -> tuple[PromoCode, Decimal]:
    """Returns (promo, discount_amount). discount_amount is clamped to at most order_amount."""
    promo = (await db.execute(
        select(PromoCode).where(func.upper(PromoCode.code) == code.strip().upper())
    )).scalar_one_or_none()

    if promo is None or not promo.is_active:
        raise PromoCodeInvalidError(internal_detail=f"promo code {code!r} not found or inactive")
    if promo.valid_until is not None and promo.valid_until < datetime.now(timezone.utc):
        raise PromoCodeInvalidError(internal_detail=f"promo code {code!r} expired at {promo.valid_until}")
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        raise PromoCodeExhaustedError(internal_detail=f"promo code {code!r} exhausted ({promo.used_count}/{promo.max_uses})")
    if promo.min_order_amount is not None and order_amount < promo.min_order_amount:
        raise PromoCodeMinOrderError(internal_detail=f"order {order_amount} below min {promo.min_order_amount}")

    user_uses = (await db.execute(
        select(func.count()).select_from(PromoCodeUsage).where(
            PromoCodeUsage.promo_code_id == promo.id, PromoCodeUsage.user_id == user_id,
        )
    )).scalar_one()
    if user_uses >= promo.max_uses_per_user:
        raise PromoCodeAlreadyUsedError(internal_detail=f"user {user_id} already used promo {code!r} {user_uses} times")

    if promo.discount_type == "PERCENT":
        discount = (order_amount * promo.discount_value / Decimal("100")).quantize(Decimal("0.01"))
    else:
        discount = promo.discount_value
    discount = min(discount, order_amount)
    return promo, discount


async def record_usage(db: AsyncSession, *, promo: PromoCode, user_id: UUID, order_id: UUID, discount_amount: Decimal) -> None:
    db.add(PromoCodeUsage(promo_code_id=promo.id, user_id=user_id, order_id=order_id, discount_amount=discount_amount))
    promo.used_count += 1
    await db.flush()

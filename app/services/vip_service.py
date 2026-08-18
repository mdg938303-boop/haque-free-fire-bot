"""
VIP tiers apply automatically -- there is nothing for the user to opt into. At checkout
we look at the user's lifetime *completed* order spend (what they actually paid, i.e.
selling_price already net of any past discounts) and grant the highest-threshold active
tier they qualify for. This is intentionally computed live rather than cached on the User
row so tier changes/deactivations by an admin take effect on the very next purchase.
"""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VipTier, Order, OrderStatus


async def create_tier(db: AsyncSession, *, name: str, min_total_spent: Decimal, discount_percent: Decimal) -> VipTier:
    tier = VipTier(name=name, min_total_spent=min_total_spent, discount_percent=discount_percent, is_active=True)
    db.add(tier)
    await db.flush()
    return tier


async def list_tiers(db: AsyncSession) -> list[VipTier]:
    return (await db.execute(select(VipTier).order_by(VipTier.min_total_spent.asc()))).scalars().all()


async def toggle_tier(db: AsyncSession, *, tier_id: UUID) -> VipTier:
    tier = await db.get(VipTier, tier_id)
    tier.is_active = not tier.is_active
    await db.flush()
    return tier


async def delete_tier(db: AsyncSession, *, tier_id: UUID) -> str:
    tier = await db.get(VipTier, tier_id)
    name = tier.name
    await db.delete(tier)
    await db.flush()
    return name


async def get_user_total_spent(db: AsyncSession, *, user_id: UUID) -> Decimal:
    total = (await db.execute(
        select(func.coalesce(func.sum(Order.selling_price), 0)).where(
            Order.user_id == user_id, Order.status == OrderStatus.COMPLETED,
        )
    )).scalar_one()
    return Decimal(total)


async def get_applicable_tier(db: AsyncSession, *, user_id: UUID) -> VipTier | None:
    total_spent = await get_user_total_spent(db, user_id=user_id)
    tiers = (await db.execute(
        select(VipTier).where(VipTier.is_active == True, VipTier.min_total_spent <= total_spent)  # noqa: E712
        .order_by(VipTier.min_total_spent.desc()).limit(1)
    )).scalar_one_or_none()
    return tiers

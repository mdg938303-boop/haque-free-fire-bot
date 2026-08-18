from decimal import Decimal, ROUND_DOWN
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderStatus, User, TransactionType
from app.services import wallet_service
from app.services.settings_service import get_setting
from app.core.exceptions import InsufficientPointsError, AppError


async def get_cashback_percent(db: AsyncSession) -> Decimal:
    cfg = await get_setting(db, "loyalty")
    try:
        return Decimal(str(cfg.get("cashback_percent", "0")))
    except Exception:  # noqa: BLE001
        return Decimal("0")


async def get_redeem_rate(db: AsyncSession) -> Decimal:
    """Points required per ৳1 of wallet credit."""
    cfg = await get_setting(db, "loyalty")
    try:
        rate = Decimal(str(cfg.get("redeem_rate", "10")))
        return rate if rate > 0 else Decimal("10")
    except Exception:  # noqa: BLE001
        return Decimal("10")


async def maybe_award_points(db: AsyncSession, *, order: Order) -> int:
    """Idempotent -- safe to call every time an order's status is touched. Only ever
    awards once per order (guarded by order.loyalty_awarded), and only when COMPLETED."""
    if order.status != OrderStatus.COMPLETED or order.loyalty_awarded:
        return 0

    percent = await get_cashback_percent(db)
    order.loyalty_awarded = True
    if percent <= 0:
        return 0

    points = int((order.selling_price * percent / Decimal("100")).to_integral_value(rounding=ROUND_DOWN))
    if points <= 0:
        return 0

    user = await db.get(User, order.user_id)
    user.loyalty_points = (user.loyalty_points or 0) + points
    order.loyalty_points_earned = points
    await db.flush()
    return points


async def redeem_points(db: AsyncSession, *, user: User, points: int) -> Decimal:
    if points <= 0:
        raise AppError(internal_detail="redeem points must be positive", user_message="❌ সঠিক পয়েন্ট সংখ্যা দিন।")
    if (user.loyalty_points or 0) < points:
        raise InsufficientPointsError(internal_detail=f"user {user.id} has {user.loyalty_points} points, tried to redeem {points}")

    rate = await get_redeem_rate(db)
    amount = (Decimal(points) / rate).quantize(Decimal("0.01"))
    if amount <= 0:
        raise AppError(internal_detail="redeem amount rounds to 0", user_message="❌ এত কম পয়েন্টে টাকা পাওয়া যাবে না, আরও পয়েন্ট জমা করুন।")

    user.loyalty_points -= points
    await wallet_service.credit_wallet(
        db, user_id=user.id, amount=amount, txn_type=TransactionType.CASHBACK,
        reference_type="loyalty_redeem", reference_id=str(user.id),
        note=f"Redeemed {points} loyalty points for ৳{amount}",
    )
    return amount

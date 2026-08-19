from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderStatus, OrderReview
from app.core.exceptions import ReviewNotAllowedError, OrderNotFoundError


async def needs_review_prompt(order: Order) -> bool:
    return order.status == OrderStatus.COMPLETED and not order.review_prompted


async def mark_review_prompted(db: AsyncSession, *, order: Order) -> None:
    order.review_prompted = True
    await db.flush()


async def submit_rating(db: AsyncSession, *, order_id: UUID, user_id: UUID, rating: int, comment: str | None = None) -> OrderReview:
    if rating < 1 or rating > 5:
        raise ReviewNotAllowedError(internal_detail=f"invalid rating {rating}")

    order = await db.get(Order, order_id)
    if order is None or order.user_id != user_id:
        raise OrderNotFoundError(internal_detail=f"order {order_id} not found for user {user_id}")
    if order.status != OrderStatus.COMPLETED:
        raise ReviewNotAllowedError(internal_detail=f"order {order.order_number} status={order.status.value}")

    existing = (await db.execute(select(OrderReview).where(OrderReview.order_id == order_id))).scalar_one_or_none()
    if existing is not None:
        existing.rating = rating
        if comment is not None:
            existing.comment = comment
        await db.flush()
        return existing

    review = OrderReview(order_id=order_id, user_id=user_id, rating=rating, comment=comment)
    db.add(review)
    await db.flush()
    return review


async def add_comment(db: AsyncSession, *, order_id: UUID, user_id: UUID, comment: str) -> OrderReview | None:
    review = (await db.execute(select(OrderReview).where(OrderReview.order_id == order_id, OrderReview.user_id == user_id))).scalar_one_or_none()
    if review is None:
        return None
    review.comment = comment
    await db.flush()
    return review


async def get_average_rating(db: AsyncSession) -> tuple[float, int]:
    row = (await db.execute(select(func.avg(OrderReview.rating), func.count(OrderReview.id)))).one()
    avg, count = row
    return (float(avg) if avg is not None else 0.0, count or 0)


async def list_recent_reviews(db: AsyncSession, limit: int = 10) -> list[OrderReview]:
    return (await db.execute(select(OrderReview).order_by(OrderReview.created_at.desc()).limit(limit))).scalars().all()

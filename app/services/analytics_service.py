from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderStatus, Deposit, DepositStatus, User


async def daily_sales(db: AsyncSession, *, days: int = 7) -> list[tuple[str, Decimal, int]]:
    """Returns [(date_str, revenue, order_count), ...] for the last `days` days, oldest
    first, one row per day even if revenue is 0 that day (so a chart has no gaps)."""
    since = datetime.now(timezone.utc) - timedelta(days=days - 1)
    since_date = since.date()

    rows = (await db.execute(
        select(
            func.date(Order.created_at).label("d"),
            func.coalesce(func.sum(Order.selling_price), 0),
            func.count(Order.id),
        )
        .where(Order.status == OrderStatus.COMPLETED, Order.created_at >= since)
        .group_by(func.date(Order.created_at))
    )).all()
    by_date = {r[0]: (Decimal(r[1]), r[2]) for r in rows}

    result = []
    for i in range(days):
        d = since_date + timedelta(days=i)
        revenue, count = by_date.get(d, (Decimal("0"), 0))
        result.append((d.strftime("%d %b"), revenue, count))
    return result


async def order_status_breakdown(db: AsyncSession, *, days: int = 30) -> dict[str, int]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await db.execute(
        select(Order.status, func.count(Order.id)).where(Order.created_at >= since).group_by(Order.status)
    )).all()
    return {status.value: count for status, count in rows}


async def top_packages(db: AsyncSession, *, days: int = 30, limit: int = 5) -> list[tuple[str, int, Decimal]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await db.execute(
        select(Order.product_name_snapshot, func.count(Order.id), func.coalesce(func.sum(Order.selling_price), 0))
        .where(Order.status == OrderStatus.COMPLETED, Order.created_at >= since)
        .group_by(Order.product_name_snapshot)
        .order_by(func.count(Order.id).desc())
        .limit(limit)
    )).all()
    return [(name, count, Decimal(revenue)) for name, count, revenue in rows]


async def summary_stats(db: AsyncSession, *, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    new_users = (await db.execute(select(func.count()).select_from(User).where(User.created_at >= since))).scalar_one()

    revenue = (await db.execute(
        select(func.coalesce(func.sum(Order.selling_price), 0)).where(
            Order.status == OrderStatus.COMPLETED, Order.created_at >= since,
        )
    )).scalar_one()
    completed_orders = (await db.execute(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.COMPLETED, Order.created_at >= since)
    )).scalar_one()
    deposits_total = (await db.execute(
        select(func.coalesce(func.sum(Deposit.amount), 0)).where(
            Deposit.status == DepositStatus.APPROVED, Deposit.created_at >= since,
        )
    )).scalar_one()

    avg_order = (Decimal(revenue) / completed_orders) if completed_orders else Decimal("0")

    return {
        "total_users": total_users, "new_users": new_users,
        "revenue": Decimal(revenue), "completed_orders": completed_orders,
        "deposits_total": Decimal(deposits_total), "avg_order_value": avg_order,
    }


def render_ascii_bar_chart(rows: list[tuple[str, Decimal, int]], *, width: int = 20) -> str:
    """rows: [(label, value, _), ...]. Renders a simple text bar chart using block
    characters -- no image library needed, so this has zero extra deploy risk on Render."""
    if not rows:
        return "(কোনো ডেটা নেই)"
    max_val = max((float(v) for _, v, _ in rows), default=0) or 1
    lines = []
    for label, value, count in rows:
        bar_len = max(1, int((float(value) / max_val) * width)) if value > 0 else 0
        bar = "█" * bar_len
        lines.append(f"{label:>6} {bar} ৳{value:.0f} ({count})")
    return "\n".join(lines)

import csv
import io
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Deposit, User


async def orders_to_csv(db: AsyncSession, *, days: int | None = 30) -> io.BytesIO:
    stmt = select(Order).order_by(Order.created_at.desc())
    if days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(Order.created_at >= since)
    orders = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Order Number", "Date", "UID", "Player Name", "Package", "Price", "Discount",
        "Promo Code", "Status", "Provider Order ID", "Error Message",
    ])
    for o in orders:
        writer.writerow([
            o.order_number, o.created_at.strftime("%Y-%m-%d %H:%M"), o.game_uid, o.player_name or "",
            o.product_name_snapshot, f"{o.selling_price:.2f}", f"{o.discount_amount:.2f}", o.promo_code or "",
            o.status.value, o.provider_order_id or "", o.error_message or "",
        ])

    out = io.BytesIO(buf.getvalue().encode("utf-8-sig"))  # BOM so Excel opens Bangla text correctly
    out.seek(0)
    return out


async def deposits_to_csv(db: AsyncSession, *, days: int | None = 30) -> io.BytesIO:
    stmt = select(Deposit).order_by(Deposit.created_at.desc())
    if days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(Deposit.created_at >= since)
    deposits = (await db.execute(stmt)).scalars().all()

    user_ids = {d.user_id for d in deposits}
    users = {}
    if user_ids:
        rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users = {u.id: u for u in rows}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Deposit Number", "Date", "Telegram Username", "Telegram ID", "Amount", "Sender Number",
        "Transaction Ref", "Status", "Admin Note",
    ])
    for d in deposits:
        u = users.get(d.user_id)
        writer.writerow([
            d.deposit_number, d.created_at.strftime("%Y-%m-%d %H:%M"),
            (u.telegram_username if u else "") or "", (u.telegram_id if u else ""),
            f"{d.amount:.2f}", d.sender_number or "", d.transaction_reference, d.status.value, d.admin_note or "",
        ])

    out = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    out.seek(0)
    return out

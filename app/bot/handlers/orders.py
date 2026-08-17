from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select, desc

from app.database import session_scope
from app.models import Order
from app.bot.handlers.start import get_or_create_user

router = Router(name="orders")

STATUS_EMOJI = {
    "PENDING": "🟡", "PROCESSING": "🟡", "COMPLETED": "🟢", "FAILED": "🔴", "CANCELED": "⚪️",
}


@router.message(F.text == "📦 আমার অর্ডার")
async def my_orders(message: Message):
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        orders = (await db.execute(
            select(Order).where(Order.user_id == user.id).order_by(desc(Order.created_at)).limit(10)
        )).scalars().all()

    if not orders:
        await message.answer("📭 আপনার কোনো অর্ডার নেই।")
        return

    lines = []
    for o in orders:
        emoji = STATUS_EMOJI.get(o.status.value, "🟡")
        lines.append(
            f"📦 Order #{o.order_number}\n"
            f"💎 {o.product_name_snapshot}\n"
            f"🆔 UID: {o.game_uid}\n"
            f"👤 {o.player_name or '-'}\n"
            f"💰 ৳{o.selling_price:.0f}\n"
            f"{emoji} {o.status.value}\n"
        )
    await message.answer("\n".join(lines))

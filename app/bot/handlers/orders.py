from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select, desc

from app.database import session_scope
from app.models import Order
from app.services.order_service import format_order_card
from app.bot.handlers.start import get_or_create_user

router = Router(name="orders")


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

    lines = [format_order_card(o) for o in orders]
    await message.answer("\n\n".join(lines))

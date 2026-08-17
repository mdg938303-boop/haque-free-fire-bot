from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select, desc

from app.database import session_scope
from app.models import WalletTransaction, TransactionType, TransactionDirection
from app.services import wallet_service
from app.bot.handlers.start import get_or_create_user

router = Router(name="wallet")

TYPE_LABELS = {
    TransactionType.DEPOSIT: "➕ Deposit",
    TransactionType.PURCHASE: "💎 Diamond Purchase",
    TransactionType.REFERRAL_BONUS: "🎁 Referral Bonus",
    TransactionType.REFUND: "🔄 Refund",
    TransactionType.ADMIN_ADJUSTMENT: "⚙️ Admin Adjustment",
}


@router.message(F.text == "💰 আমার ব্যালেন্স")
async def show_balance(message: Message):
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        wallet = await wallet_service.get_or_create_wallet(db, user.id)

    text = (
        "💰 <b>আমার ব্যালেন্স</b>\n\n"
        f"বর্তমান ব্যালেন্স: ৳{wallet.balance:.2f}\n"
        f"➕ মোট ডিপোজিট: ৳{wallet.total_deposit:.2f}\n"
        f"💎 মোট খরচ: ৳{wallet.total_purchase:.2f}\n"
        f"🎁 রেফারেল আয়: ৳{wallet.total_referral_income:.2f}\n"
        f"🔄 মোট রিফান্ড: ৳{wallet.total_refund:.2f}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💳 লেনদেন")
async def show_transactions(message: Message):
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        wallet = await wallet_service.get_or_create_wallet(db, user.id)
        txns = (await db.execute(
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet.id)
            .order_by(desc(WalletTransaction.created_at))
            .limit(15)
        )).scalars().all()

    if not txns:
        await message.answer("📭 কোনো লেনদেন পাওয়া যায়নি।")
        return

    lines = ["💳 <b>সাম্প্রতিক লেনদেন</b>\n"]
    for t in txns:
        sign = "+" if t.direction == TransactionDirection.CREDIT else "-"
        lines.append(
            f"{TYPE_LABELS.get(t.type, t.type.value)}\n"
            f"{sign}৳{t.amount:.2f} | ব্যালেন্স: ৳{t.balance_after:.2f}\n"
            f"{t.created_at.strftime('%d %b %Y, %I:%M %p')}\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")

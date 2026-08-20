from decimal import Decimal, InvalidOperation

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope
from app.models import PaymentMethod
from app.services import deposit_service
from app.core.exceptions import AppError
from app.bot.states import DepositStates
from app.bot.keyboards import payment_methods_kb, cancel_kb, main_menu_kb, admin_deposit_actions_kb
from app.bot.handlers.start import get_or_create_user

settings = get_settings()
router = Router(name="deposit")


async def _show_payment_methods(message: Message):
    async with session_scope() as db:
        methods = (await db.execute(
            select(PaymentMethod).where(PaymentMethod.is_active == True).order_by(PaymentMethod.sort_order.asc())  # noqa: E712
        )).scalars().all()

    if not methods:
        await message.answer("⚠️ এই মুহূর্তে কোনো পেমেন্ট মেথড সক্রিয় নেই।")
        return
    await message.answer("➕ পেমেন্ট মেথড বেছে নিন:", reply_markup=payment_methods_kb(methods))


@router.message(F.text == "➕ টাকা জমা দিন")
async def start_deposit(message: Message):
    await _show_payment_methods(message)


@router.callback_query(F.data == "go_deposit")
async def go_deposit_callback(callback: CallbackQuery):
    await _show_payment_methods(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("select_payment_method:"))
async def select_payment_method(callback: CallbackQuery, state: FSMContext):
    method_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        method = await db.get(PaymentMethod, method_id)

    if method is None:
        await callback.answer("মেথড পাওয়া যায়নি", show_alert=True)
        return

    await state.set_state(DepositStates.waiting_amount)
    await state.update_data(payment_method_id=str(method.id))

    text = f"💳 <b>{method.name}</b>\n\n"
    text += f"📱 নাম্বার: <code>{method.account_number}</code> ({method.account_type})\n"
    if method.instructions:
        text += f"\nℹ️ {method.instructions}\n"
    text += "\n💰 কত টাকা জমা দিতে চান? (শুধু সংখ্যা লিখুন)"

    await callback.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb())
    await callback.answer()


@router.message(DepositStates.waiting_amount, F.text)
async def receive_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ সঠিক পরিমাণ লিখুন (যেমন: 100)")
        return

    await state.update_data(amount=str(amount))
    await state.set_state(DepositStates.waiting_reference)
    await message.answer(
        "🧾 আপনার Transaction ID / Reference নাম্বারটি লিখুন\n"
        "(যে নাম্বার থেকে পাঠিয়েছেন সেটিও লিখতে পারেন, যেমন: TrxID SenderNumber)"
    )


@router.message(DepositStates.waiting_reference, F.text)
async def receive_reference(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    parts = message.text.strip().split()
    reference = parts[0]
    sender_number = parts[1] if len(parts) > 1 else None

    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        method = await db.get(PaymentMethod, data["payment_method_id"])
        try:
            deposit = await deposit_service.create_deposit(
                db,
                user_id=user.id,
                payment_method_id=data["payment_method_id"],
                amount=Decimal(data["amount"]),
                sender_number=sender_number,
                transaction_reference=reference,
            )
        except AppError as err:
            await state.clear()
            await message.answer(err.user_message, reply_markup=main_menu_kb())
            return
        deposit_id, method_name = deposit.id, method.name if method else "-"
        uname = f"@{user.telegram_username}" if user.telegram_username else (user.full_name or str(user.telegram_id))

    await state.clear()
    await message.answer(
        f"✅ আপনার ডিপোজিট রিকোয়েস্ট জমা হয়েছে।\n\n"
        f"🧾 Deposit ID: {deposit.deposit_number}\n"
        f"💰 পরিমাণ: ৳{deposit.amount:.2f}\n"
        f"⏳ স্ট্যাটাস: অ্যাডমিন যাচাই করার অপেক্ষায়\n\n"
        f"অনুমোদনের পর আপনার ব্যালেন্সে টাকা যোগ হবে।",
        reply_markup=main_menu_kb(),
    )

    admin_text = (
        f"💳 <b>নতুন ডিপোজিট রিকোয়েস্ট</b>\n\n"
        f"👤 ইউজার: {uname}\n"
        f"🧾 Deposit ID: {deposit.deposit_number}\n"
        f"💰 পরিমাণ: ৳{deposit.amount:.2f}\n"
        f"💳 মেথড: {method_name}\n"
        f"🔢 Reference: <code>{reference}</code>\n"
        + (f"📱 প্রেরকের নাম্বার: {sender_number}\n" if sender_number else "")
    )
    for admin_id in settings.telegram_admin_id_list:
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="HTML", reply_markup=admin_deposit_actions_kb(deposit_id))
        except Exception:  # noqa: BLE001 - one admin's chat being unreachable must not block others
            continue

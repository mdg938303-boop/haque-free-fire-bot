from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.database import session_scope
from app.services import loyalty_service
from app.core.exceptions import AppError
from app.bot.states import LoyaltyStates
from app.bot.keyboards import loyalty_kb, cancel_kb, main_menu_kb
from app.bot.handlers.start import get_or_create_user

router = Router(name="loyalty")


@router.message(F.text == "🎯 লয়্যালটি পয়েন্ট")
async def show_loyalty(message: Message):
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        rate = await loyalty_service.get_redeem_rate(db)
        points = user.loyalty_points or 0
        redeemable = (points / rate) if rate else 0

    text = (
        f"🎯 <b>আপনার লয়্যালটি পয়েন্ট</b>\n\n"
        f"💠 বর্তমান পয়েন্ট: {points}\n"
        f"💱 রেট: {rate:.0f} পয়েন্ট = ৳1\n"
        f"💰 এখন রিডিম করলে পাবেন: ৳{redeemable:.2f}\n\n"
        f"প্রতিটি সম্পন্ন অর্ডারে আপনি পয়েন্ট পাবেন, যা পরে ওয়ালেট ব্যালেন্সে রূপান্তর করা যায়।"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=loyalty_kb())


@router.callback_query(F.data == "redeem_points")
async def start_redeem(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LoyaltyStates.waiting_redeem_points)
    await callback.message.answer("💱 কত পয়েন্ট রিডিম করতে চান? (শুধু সংখ্যা লিখুন)", reply_markup=cancel_kb())
    await callback.answer()


@router.message(LoyaltyStates.waiting_redeem_points, F.text)
async def process_redeem(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ সঠিক একটি সংখ্যা দিন।", reply_markup=main_menu_kb())
        return

    points = int(text)
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        try:
            amount = await loyalty_service.redeem_points(db, user=user, points=points)
        except AppError as err:
            await message.answer(err.user_message, reply_markup=main_menu_kb())
            return

    await message.answer(
        f"✅ {points} পয়েন্ট রিডিম করে ৳{amount} আপনার ওয়ালেটে যোগ করা হয়েছে।",
        reply_markup=main_menu_kb(),
    )

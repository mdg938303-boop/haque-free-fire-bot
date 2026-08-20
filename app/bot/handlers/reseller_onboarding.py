from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope
from app.models import User
from app.services import referral_service, reseller_service, reseller_application_service
from app.core.exceptions import AppError
from app.bot.states import OnboardingStates, ResellerApplyStates
from app.bot.keyboards import (
    main_menu_kb, onboarding_choice_kb, reseller_login_or_apply_kb, cancel_kb, reseller_apply_admin_kb,
)
from app.bot.handlers.start import get_or_create_user

settings = get_settings()
router = Router(name="reseller_onboarding")


async def _finish_customer_signup(message_or_callback, tg_user, state: FSMContext):
    data = await state.get_data()
    ref_code = data.get("pending_ref_code")
    await state.clear()

    async with session_scope() as db:
        existing = (await db.execute(select(User).where(User.telegram_id == tg_user.id))).scalar_one_or_none()
        is_new = existing is None
        user = await get_or_create_user(db, tg_user)
        if is_new and ref_code:
            await referral_service.attribute_signup(db, new_user=user, referral_code=ref_code)

    await message_or_callback.answer(
        "✅ আপনার Customer অ্যাকাউন্ট তৈরি হয়েছে!\n\nনিচের মেনু থেকে যেকোনো অপশন বেছে নিন 👇",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "onboard_customer")
async def onboard_customer(callback: CallbackQuery, state: FSMContext):
    await _finish_customer_signup(callback.message, callback.from_user, state)
    await callback.answer()


@router.callback_query(F.data == "onboard_reseller")
async def onboard_reseller(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏪 <b>Reseller Login</b>\n\nআপনার কাছে ইউজারনেম/পাসওয়ার্ড থাকলে Login করুন, অথবা না থাকলে আবেদন করুন।",
        parse_mode="HTML", reply_markup=reseller_login_or_apply_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "onboard_back")
async def onboard_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "আপনি কী ধরনের অ্যাকাউন্ট ব্যবহার করবেন?", reply_markup=onboarding_choice_kb(),
    )
    await callback.answer()


# =============================================================== LOGIN =====
@router.callback_query(F.data == "reseller_login_start")
async def reseller_login_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OnboardingStates.waiting_reseller_username)
    await callback.message.answer("🆔 ইউজারনেম দিন:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(OnboardingStates.waiting_reseller_username, F.text)
async def reseller_username_received(message: Message, state: FSMContext):
    await state.update_data(reseller_username=message.text.strip())
    await state.set_state(OnboardingStates.waiting_reseller_password)
    await message.answer("🔑 পাসওয়ার্ড দিন:", reply_markup=cancel_kb())


@router.message(OnboardingStates.waiting_reseller_password, F.text)
async def reseller_password_received(message: Message, state: FSMContext):
    data = await state.get_data()
    username = data.get("reseller_username")
    ref_code = data.get("pending_ref_code")
    await state.clear()

    try:
        # delete the password message from chat history where possible (best-effort privacy)
        await message.delete()
    except Exception:  # noqa: BLE001
        pass

    async with session_scope() as db:
        try:
            reseller = await reseller_service.authenticate(
                db, username=username, password=message.text.strip(), telegram_id=message.from_user.id,
            )
        except AppError as err:
            await message.answer(err.user_message)
            return

        is_newly_bound = reseller.bound_at is not None
        existing = (await db.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
        is_new_user = existing is None
        user = await get_or_create_user(db, message.from_user)
        if is_new_user and ref_code:
            await referral_service.attribute_signup(db, new_user=user, referral_code=ref_code)

    await message.answer(
        f"✅ Login সফল! স্বাগতম, {reseller.username}।\n\nনিচের মেনু থেকে যেকোনো অপশন বেছে নিন 👇",
        reply_markup=main_menu_kb(),
    )


# ============================================================= APPLY =======
@router.callback_query(F.data == "reseller_apply_start")
async def reseller_apply_start(callback: CallbackQuery, state: FSMContext):
    async with session_scope() as db:
        await get_or_create_user(db, callback.from_user)  # ensure a row exists to attach the application to
    await state.set_state(ResellerApplyStates.waiting_message)
    await callback.message.answer(
        "📝 কেন আপনি Reseller হতে চান তা সংক্ষেপে লিখুন (না লিখতে চাইলে - পাঠান):",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(ResellerApplyStates.waiting_message, F.text)
async def reseller_apply_message_received(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    note = None if message.text.strip() == "-" else message.text.strip()

    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        try:
            application = await reseller_application_service.create_application(
                db, user_id=user.id, telegram_id=message.from_user.id, message=note,
            )
        except AppError as err:
            await message.answer(err.user_message, reply_markup=main_menu_kb())
            return
        application_id = application.id
        uname = f"@{user.telegram_username}" if user.telegram_username else (user.full_name or str(user.telegram_id))

    await message.answer(
        "✅ আপনার আবেদন জমা হয়েছে। Admin পর্যালোচনা করার পর জানানো হবে। ততক্ষণ Customer হিসেবে বট ব্যবহার করতে পারবেন।",
        reply_markup=main_menu_kb(),
    )

    admin_text = f"📝 <b>নতুন Reseller আবেদন</b>\n\nফ্রম: {uname}\nবার্তা: {note or '-'}"
    for admin_id in settings.telegram_admin_id_list:
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="HTML", reply_markup=reseller_apply_admin_kb(application_id))
        except Exception:  # noqa: BLE001
            continue

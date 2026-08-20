from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select, func

from app.database import session_scope
from app.models import User, Wallet, Referral, ResellerApplication
from app.services import wallet_service, referral_service, reseller_service
from app.services.settings_service import get_setting
from app.core.security import generate_referral_code
from app.bot.states import OnboardingStates
from app.bot.keyboards import main_menu_kb, support_kb, support_menu_kb, onboarding_choice_kb, cancel_kb, reseller_apply_only_kb

router = Router(name="start")


async def get_or_create_user(db, tg_user) -> User:
    result = await db.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=tg_user.id,
            telegram_username=tg_user.username,
            full_name=tg_user.full_name,
            referral_code=generate_referral_code(tg_user.id),
        )
        db.add(user)
        await db.flush()
        await wallet_service.get_or_create_wallet(db, user.id)
    else:
        user.telegram_username = tg_user.username
        user.full_name = tg_user.full_name
    return user


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    ref_code = args[1].strip() if len(args) > 1 else None

    async with session_scope() as db:
        existing_user = (await db.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
        bound_reseller = await reseller_service.get_by_telegram_id(db, telegram_id=message.from_user.id)
        if bound_reseller is not None:
            await reseller_service.deactivate_session(db, reseller_id=bound_reseller.id)

    if existing_user is None:
        # Brand new Telegram account -- ask Customer vs Reseller before creating any row,
        # so this screen never re-appears once they've made a choice (see the other two
        # branches below, which handle every OTHER kind of returning visitor).
        await state.update_data(pending_ref_code=ref_code)
        await message.answer(
            "👋 স্বাগতম Free Fire Diamond Top-Up বটে!\n\nআপনি কী ধরনের অ্যাকাউন্ট ব্যবহার করবেন?",
            reply_markup=onboarding_choice_kb(),
        )
        return

    if bound_reseller is not None and bound_reseller.status == "ACTIVE":
        # Returning, already-linked reseller -- re-authenticate every single /start (per spec).
        await state.set_state(OnboardingStates.waiting_reseller_username)
        await message.answer("🏪 Reseller Login\n\n🆔 ইউজারনেম দিন:", reply_markup=cancel_kb())
        return

    # Ordinary returning customer.
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
    await message.answer(
        "👋 আবার স্বাগতম!\n\nনিচের মেনু থেকে যেকোনো অপশন বেছে নিন 👇",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "👤 আমার প্রোফাইল")
async def profile_handler(message: Message):
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        wallet = await wallet_service.get_or_create_wallet(db, user.id)
        order_count = (await db.execute(select(func.count()).select_from(User).where(User.id == user.id))).scalar()
        from app.models import Order
        total_orders = (await db.execute(select(func.count()).select_from(Order).where(Order.user_id == user.id))).scalar()
        referral_count = (await db.execute(select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id))).scalar()

        reseller = await reseller_service.get_by_telegram_id(db, telegram_id=user.telegram_id)
        pending_application = (await db.execute(
            select(ResellerApplication).where(ResellerApplication.user_id == user.id, ResellerApplication.status == "PENDING")
        )).scalar_one_or_none()

    text = (
        "👤 <b>আমার প্রোফাইল</b>\n\n"
        f"নাম: {user.full_name or '-'}\n"
        f"ইউজারনেম: @{user.telegram_username or '-'}\n"
        f"Telegram ID: <code>{user.telegram_id}</code>\n"
        f"💰 ব্যালেন্স: ৳{wallet.balance:.2f}\n"
        f"📦 মোট অর্ডার: {total_orders}\n"
        f"➕ মোট ডিপোজিট: ৳{wallet.total_deposit:.2f}\n"
        f"💎 মোট খরচ: ৳{wallet.total_purchase:.2f}\n"
        f"🎁 রেফারেল সংখ্যা: {referral_count}\n"
        f"📅 যোগদান: {user.created_at.strftime('%d %b %Y')}"
    )
    if reseller is not None and reseller.status == "ACTIVE":
        text += f"\n\n🏪 <b>Reseller অ্যাকাউন্ট</b> (Username: {reseller.username})"
        await message.answer(text, parse_mode="HTML")
        return
    if pending_application is not None:
        text += "\n\n📝 আপনার Reseller আবেদন পর্যালোচনাধীন।"
        await message.answer(text, parse_mode="HTML")
        return

    await message.answer(text, parse_mode="HTML", reply_markup=reseller_apply_only_kb())


@router.message(F.text == "🎁 রেফার & আয়")
async def referral_handler(message: Message):
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        settings = await referral_service.get_referral_settings(db)
        referral_count = (await db.execute(select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id))).scalar()
        total_earnings = (await wallet_service.get_or_create_wallet(db, user.id)).total_referral_income
        general = await get_setting(db, "general")
        bot_uname = general.get("bot_username") or "your_bot"

    if not settings.get("enabled"):
        await message.answer("⚠️ রেফারেল প্রোগ্রাম বর্তমানে বন্ধ আছে।")
        return

    link = f"https://t.me/{bot_uname}?start={user.referral_code}"
    text = (
        "🎁 <b>রেফার করে আয় করুন</b>\n\n"
        f"🔗 আপনার রেফারেল লিংক:\n<code>{link}</code>\n\n"
        f"👥 মোট রেফারেল: {referral_count}\n"
        f"💰 মোট আয়: ৳{total_earnings:.2f}\n\n"
        f"বোনাস: প্রতি রেফারেলের প্রথম ডিপোজিটে আপনি পাবেন ৳{settings.get('bonus_amount', 0)}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📞 সাপোর্ট")
async def support_handler(message: Message):
    async with session_scope() as db:
        general = await get_setting(db, "general")
    support_username = general.get("support_username") or "support"
    await message.answer(
        "📞 যেকোনো সমস্যায় আমাদের সাপোর্টে যোগাযোগ করুন, অথবা বটের ভেতরেই একটা টিকেট খুলুন।",
        reply_markup=support_menu_kb(support_username),
    )


@router.message(F.text == "🔙 ফিরে যান")
async def back_to_menu(message: Message):
    await message.answer("প্রধান মেনু 👇", reply_markup=main_menu_kb())

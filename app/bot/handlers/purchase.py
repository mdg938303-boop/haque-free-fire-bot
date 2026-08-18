from decimal import Decimal

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, update

from app.database import session_scope
from app.models import Package, Order
from app.services import order_service, wallet_service
from app.core.exceptions import AppError
from app.bot.states import PurchaseStates
from app.bot.keyboards import packages_kb, cancel_kb, confirm_purchase_kb, insufficient_balance_kb, main_menu_kb
from app.bot.handlers.start import get_or_create_user

router = Router(name="purchase")


@router.message(F.text == "💎 ডায়মন্ড কিনুন")
async def show_packages(message: Message):
    async with session_scope() as db:
        packages = (await db.execute(
            select(Package).where(Package.is_active == True).order_by(Package.sort_order.asc())  # noqa: E712
        )).scalars().all()

    if not packages:
        await message.answer("⚠️ এই মুহূর্তে কোনো প্যাকেজ উপলব্ধ নেই।")
        return

    await message.answer("💎 একটি প্যাকেজ বেছে নিন:", reply_markup=packages_kb(packages))


async def _show_confirmation(target: Message, state: FSMContext, package_id: str, uid: str):
    """Shared by both entry points (manual UID entry, and 'এই UID-তে Diamond কিনুন' shortcut)
    so a UID that's already known is never asked for twice."""
    async with session_scope() as db:
        package = await db.get(Package, package_id)
        if package is None or not package.is_active:
            await state.clear()
            await target.answer("❌ প্যাকেজটি বর্তমানে বন্ধ আছে।", reply_markup=main_menu_kb())
            return
        try:
            player_name, provider_product, provider = await order_service.validate_uid_for_package(
                db, package_id=package.id, uid=uid
            )
        except AppError as err:
            await state.clear()
            await target.answer(err.user_message, reply_markup=main_menu_kb())
            return

        await state.update_data(
            package_id=str(package.id), uid=uid, player_name=player_name,
            provider_product_id=str(provider_product.id),
        )
        await state.set_state(PurchaseStates.confirming)

        text = (
            f"💎 Package: {package.diamond_amount} Diamonds\n\n"
            f"🆔 UID: {uid}\n👤 Player: {player_name}\n\n"
            f"💰 Price: ৳{package.selling_price:.0f}"
        )
    await target.answer(text, reply_markup=confirm_purchase_kb())


@router.callback_query(F.data.startswith("select_package:"))
async def select_package(callback: CallbackQuery, state: FSMContext):
    package_id = callback.data.split(":", 1)[1]
    data = await state.get_data()
    known_uid = data.get("known_uid")

    if known_uid:
        # UID was already validated via "🔎 চেক UID" -- skip asking for it again.
        await callback.answer()
        await _show_confirmation(callback.message, state, package_id, known_uid)
        return

    await state.set_state(PurchaseStates.waiting_uid)
    await state.update_data(package_id=package_id)
    await callback.message.answer("🆔 Free Fire UID দিন", reply_markup=cancel_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("buy_for_uid:"))
async def buy_for_checked_uid(callback: CallbackQuery, state: FSMContext):
    # From the "🔎 চেক UID" success screen -- the UID is already validated, only the
    # package still needs picking, so we remember it and skip the UID prompt afterwards.
    uid = callback.data.split(":", 1)[1]
    if uid and uid != "choose" and uid.isdigit():
        await state.update_data(known_uid=uid)
    async with session_scope() as db:
        packages = (await db.execute(
            select(Package).where(Package.is_active == True).order_by(Package.sort_order.asc())  # noqa: E712
        )).scalars().all()
    await callback.message.answer("💎 একটি প্যাকেজ বেছে নিন:", reply_markup=packages_kb(packages))
    await callback.answer()


@router.message(PurchaseStates.waiting_uid, F.text)
async def receive_uid(message: Message, state: FSMContext):
    uid = message.text.strip()
    if not uid.isdigit():
        await message.answer("❌ সঠিক UID দিন (শুধু সংখ্যা)।")
        return

    data = await state.get_data()
    await _show_confirmation(message, state, data["package_id"], uid)


@router.callback_query(PurchaseStates.confirming, F.data == "confirm_purchase")
async def confirm_purchase(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    async with session_scope() as db:
        user = await get_or_create_user(db, callback.from_user)
        package = await db.get(Package, data["package_id"])
        wallet = await wallet_service.get_or_create_wallet(db, user.id)

        if wallet.balance < package.selling_price:
            await callback.message.answer(
                "❌ আপনার ব্যালেন্স পর্যাপ্ত নয়।", reply_markup=insufficient_balance_kb()
            )
            await callback.answer()
            return

        try:
            player_name, provider_product, provider = await order_service.validate_uid_for_package(
                db, package_id=package.id, uid=data["uid"]
            )
            order = await order_service.create_order(
                db, user=user, package=package, uid=data["uid"], player_name=player_name,
                provider_product=provider_product, provider=provider,
            )
        except AppError as err:
            await callback.message.answer(err.user_message, reply_markup=main_menu_kb())
            await callback.answer()
            return

        card_text = order_service.format_order_card(order)
        order_id = order.id

    sent = await callback.message.answer(card_text, reply_markup=main_menu_kb())

    # Remember which chat/message this order's card lives in, so the background poller
    # can edit this same message in place once the status changes (PROCESSING -> COMPLETED/FAILED)
    # instead of spamming a new message.
    async with session_scope() as db:
        await db.execute(
            update(Order).where(Order.id == order_id).values(
                telegram_chat_id=sent.chat.id, telegram_message_id=sent.message_id,
            )
        )
    await callback.answer()


@router.callback_query(F.data == "cancel_purchase")
async def cancel_purchase(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ অর্ডার বাতিল করা হয়েছে।", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "go_menu")
async def go_menu(callback: CallbackQuery):
    await callback.message.answer("প্রধান মেনু 👇", reply_markup=main_menu_kb())
    await callback.answer()

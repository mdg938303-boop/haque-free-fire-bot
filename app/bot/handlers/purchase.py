from decimal import Decimal

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, User as TgUser
from sqlalchemy import select, update

from app.database import session_scope
from app.models import Package, Order
from app.services import order_service, wallet_service, vip_service, promo_service
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


async def _show_confirmation(
    target: Message, tg_user: TgUser, state: FSMContext, package_id: str, uid: str, promo_code: str | None = None,
):
    """Shared by both entry points (manual UID entry, and 'এই UID-তে Diamond কিনুন' shortcut)
    so a UID that's already known is never asked for twice. Also (re)computes pricing:
    automatic VIP tier discount + an optional promo code, stacked."""
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

        user = await get_or_create_user(db, tg_user)

        base_price = package.selling_price
        vip_tier = await vip_service.get_applicable_tier(db, user_id=user.id)
        vip_discount_percent = vip_tier.discount_percent if vip_tier else None
        price_after_vip = (
            (base_price * (Decimal("100") - vip_discount_percent) / Decimal("100")).quantize(Decimal("0.01"))
            if vip_discount_percent else base_price
        )

        promo_discount = Decimal("0")
        applied_promo_code = None
        if promo_code:
            try:
                promo, promo_discount = await promo_service.validate_and_price(
                    db, code=promo_code, user_id=user.id, order_amount=price_after_vip
                )
                applied_promo_code = promo.code
            except AppError as err:
                await target.answer(err.user_message)
                # fall through with no promo applied rather than blocking the whole purchase

        final_price = max(price_after_vip - promo_discount, Decimal("0"))
        discount_amount = base_price - final_price

        await state.update_data(
            package_id=str(package.id), uid=uid, player_name=player_name,
            provider_product_id=str(provider_product.id),
            final_price=str(final_price), discount_amount=str(discount_amount),
            vip_discount_percent=str(vip_discount_percent) if vip_discount_percent else "",
            promo_code=applied_promo_code or "",
        )
        await state.set_state(PurchaseStates.confirming)

        lines = [f"💎 Package: {package.diamond_amount} Diamonds", "", f"🆔 UID: {uid}\n👤 Player: {player_name}", ""]
        if discount_amount > 0:
            lines.append(f"💵 মূল্য: ৳{base_price:.0f} → ছাড়ের পর ৳{final_price:.0f}")
            bits = []
            if vip_discount_percent:
                bits.append(f"VIP {vip_discount_percent:.0f}%")
            if applied_promo_code:
                bits.append(f"প্রোমো '{applied_promo_code}'")
            lines.append(f"🏷️ ছাড়: {' + '.join(bits)}")
        else:
            lines.append(f"💰 Price: ৳{final_price:.0f}")
        text = "\n".join(lines)
    await target.answer(text, reply_markup=confirm_purchase_kb(promo_applied=bool(applied_promo_code)))


@router.callback_query(F.data.startswith("select_package:"))
async def select_package(callback: CallbackQuery, state: FSMContext):
    package_id = callback.data.split(":", 1)[1]
    data = await state.get_data()
    known_uid = data.get("known_uid")

    if known_uid:
        # UID was already validated via "🔎 চেক UID" -- skip asking for it again.
        await callback.answer()
        await _show_confirmation(callback.message, callback.from_user, state, package_id, known_uid)
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
    await _show_confirmation(message, message.from_user, state, data["package_id"], uid)


@router.callback_query(PurchaseStates.confirming, F.data == "enter_promo_code")
async def ask_promo_code(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await state.set_state(PurchaseStates.waiting_promo_code)
    await callback.message.answer("🏷️ আপনার প্রোমো কোড লিখুন:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(PurchaseStates.waiting_promo_code, F.text)
async def receive_promo_code(message: Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    await _show_confirmation(message, message.from_user, state, data["package_id"], data["uid"], promo_code=code)


@router.callback_query(PurchaseStates.confirming, F.data == "confirm_purchase")
async def confirm_purchase(callback: CallbackQuery, state: FSMContext):
    # Remove the Confirm/Cancel/Promo buttons immediately so this message can't be
    # acted on twice while the order is being processed.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    data = await state.get_data()
    await state.clear()

    final_price = Decimal(data["final_price"])
    discount_amount = Decimal(data.get("discount_amount", "0"))
    vip_discount_percent = Decimal(data["vip_discount_percent"]) if data.get("vip_discount_percent") else None
    promo_code = data.get("promo_code") or None

    async with session_scope() as db:
        user = await get_or_create_user(db, callback.from_user)
        package = await db.get(Package, data["package_id"])
        wallet = await wallet_service.get_or_create_wallet(db, user.id)

        if wallet.balance < final_price:
            await callback.message.answer(
                "❌ আপনার ব্যালেন্স পর্যাপ্ত নয়।", reply_markup=insufficient_balance_kb()
            )
            await callback.answer()
            return

        promo_obj = None
        if promo_code:
            vip_only_price = (
                (package.selling_price * (Decimal("100") - vip_discount_percent) / Decimal("100")).quantize(Decimal("0.01"))
                if vip_discount_percent else package.selling_price
            )
            try:
                promo_obj, _ = await promo_service.validate_and_price(
                    db, code=promo_code, user_id=user.id, order_amount=vip_only_price,
                )
            except AppError:
                # promo became invalid/exhausted between confirm-screen and tap (race) --
                # proceed at the VIP-only price rather than blocking the purchase entirely.
                promo_code = None
                final_price = vip_only_price
                discount_amount = package.selling_price - vip_only_price

        try:
            player_name, provider_product, provider = await order_service.validate_uid_for_package(
                db, package_id=package.id, uid=data["uid"]
            )
            order = await order_service.create_order(
                db, user=user, package=package, uid=data["uid"], player_name=player_name,
                provider_product=provider_product, provider=provider,
                final_price=final_price, discount_amount=discount_amount,
                promo_code=promo_code, vip_discount_percent=vip_discount_percent,
            )
        except AppError as err:
            await callback.message.answer(err.user_message, reply_markup=main_menu_kb())
            await callback.answer()
            return

        if promo_obj is not None:
            await promo_service.record_usage(
                db, promo=promo_obj, user_id=user.id, order_id=order.id, discount_amount=discount_amount,
            )

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
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.message.answer("❌ অর্ডার বাতিল করা হয়েছে।", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "go_menu")
async def go_menu(callback: CallbackQuery):
    await callback.message.answer("প্রধান মেনু 👇", reply_markup=main_menu_kb())
    await callback.answer()

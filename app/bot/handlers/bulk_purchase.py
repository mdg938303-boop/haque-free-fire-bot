from decimal import Decimal

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.database import session_scope
from app.models import Package
from app.services import order_service, wallet_service, vip_service, reseller_service
from app.services.settings_service import get_setting
from app.core.exceptions import AppError
from app.bot.states import BulkPurchaseStates
from app.bot.handlers.start import get_or_create_user
from app.bot.keyboards import bulk_packages_kb, cancel_kb, bulk_confirm_kb, insufficient_balance_kb, main_menu_kb

router = Router(name="bulk_purchase")


@router.message(F.text == "🎁 বাল্ক অর্ডার")
async def bulk_start(message: Message):
    async with session_scope() as db:
        packages = (await db.execute(
            select(Package).where(Package.is_active == True).order_by(Package.sort_order.asc())  # noqa: E712
        )).scalars().all()
        packages = await reseller_service.visible_packages_for(db, telegram_id=message.from_user.id, all_packages=packages)
    if not packages:
        await message.answer("⚠️ এই মুহূর্তে কোনো প্যাকেজ উপলব্ধ নেই।")
        return
    await message.answer(
        "🎁 <b>বাল্ক অর্ডার</b>\n\nএকই প্যাকেজ একসাথে একাধিক UID-তে পাঠাতে চাইলে ব্যবহার করুন। প্রথমে প্যাকেজ বেছে নিন:",
        parse_mode="HTML", reply_markup=bulk_packages_kb(packages),
    )


@router.callback_query(F.data.startswith("bulk_select_package:"))
async def bulk_package_selected(callback: CallbackQuery, state: FSMContext):
    package_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        cfg = await get_setting(db, "topup")
    max_uids = int(cfg.get("max_bulk_uids", 20))
    await state.update_data(package_id=package_id)
    await state.set_state(BulkPurchaseStates.waiting_uids)
    await callback.message.answer(
        f"🆔 প্রতি লাইনে একটি করে UID দিন (সর্বোচ্চ {max_uids}টি):", reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(BulkPurchaseStates.waiting_uids, F.text)
async def bulk_uids_received(message: Message, state: FSMContext):
    raw_uids = [u.strip() for u in message.text.replace(",", "\n").split("\n")]
    uids = list(dict.fromkeys(u for u in raw_uids if u))  # de-dupe, preserve order

    async with session_scope() as db:
        cfg = await get_setting(db, "topup")
        max_uids = int(cfg.get("max_bulk_uids", 20))

    if not uids:
        await message.answer("❌ অন্তত একটি UID দিন।")
        return
    if len(uids) > max_uids:
        await message.answer(f"❌ সর্বোচ্চ {max_uids}টি UID দেওয়া যাবে, আপনি {len(uids)}টি দিয়েছেন।")
        return
    non_digit = [u for u in uids if not u.isdigit()]
    if non_digit:
        await message.answer(f"❌ এই UID(গুলো) সঠিক নয় (শুধু সংখ্যা হতে হবে): {', '.join(non_digit)}")
        return

    data = await state.get_data()
    package_id = data["package_id"]

    async with session_scope() as db:
        package = await db.get(Package, package_id)
        if package is None or not package.is_active:
            await state.clear()
            await message.answer("❌ প্যাকেজটি বর্তমানে বন্ধ আছে।", reply_markup=main_menu_kb())
            return

        user = await get_or_create_user(db, message.from_user)
        try:
            reseller_base_price = await reseller_service.get_base_price(db, telegram_id=message.from_user.id, package=package)
        except AppError as err:
            await state.clear()
            await message.answer(err.user_message, reply_markup=main_menu_kb())
            return
        vip_tier = await vip_service.get_applicable_tier(db, user_id=user.id)
        vip_discount_percent = vip_tier.discount_percent if vip_tier else None
        unit_price = (
            (reseller_base_price * (Decimal("100") - vip_discount_percent) / Decimal("100")).quantize(Decimal("0.01"))
            if vip_discount_percent else reseller_base_price
        )

        valid, invalid = [], []
        for uid in uids:
            try:
                player_name, provider_product, provider = await order_service.validate_uid_for_package(
                    db, package_id=package.id, uid=uid
                )
                valid.append({"uid": uid, "player_name": player_name, "provider_product_id": str(provider_product.id)})
            except AppError as err:
                invalid.append((uid, err.user_message))

    if not valid:
        await state.clear()
        await message.answer("❌ কোনো UID-ই বৈধ পাওয়া যায়নি:\n" + "\n".join(f"• {u}: {m}" for u, m in invalid), reply_markup=main_menu_kb())
        return

    total_price = unit_price * len(valid)
    await state.update_data(
        valid_uids=valid, unit_price=str(unit_price), total_price=str(total_price),
        vip_discount_percent=str(vip_discount_percent) if vip_discount_percent else "",
    )
    await state.set_state(BulkPurchaseStates.confirming)

    lines = [f"🎁 <b>বাল্ক অর্ডার সামারি</b>\n", f"💎 Package: {package.diamond_amount} Diamonds"]
    if unit_price != package.selling_price:
        lines.append(f"🏷️ ছাড়সহ প্রতি UID: ৳{package.selling_price:.0f} → ৳{unit_price:.0f}")
    lines.append(f"\n✅ বৈধ UID ({len(valid)}টি):")
    for v in valid:
        lines.append(f"  • {v['uid']} — {v['player_name']}")
    if invalid:
        lines.append(f"\n❌ বাদ দেওয়া হয়েছে ({len(invalid)}টি):")
        for u, m in invalid:
            lines.append(f"  • {u}: {m}")
    lines.append(f"\n💰 মোট মূল্য: ৳{total_price:.0f} ({len(valid)} × ৳{unit_price:.0f})")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=bulk_confirm_kb())


@router.callback_query(BulkPurchaseStates.confirming, F.data == "bulk_confirm")
async def bulk_confirm(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass

    data = await state.get_data()
    await state.clear()

    package_id = data["package_id"]
    unit_price = Decimal(data["unit_price"])
    total_price = Decimal(data["total_price"])
    vip_discount_percent = Decimal(data["vip_discount_percent"]) if data.get("vip_discount_percent") else None
    valid = data["valid_uids"]
    discount_per_unit = None

    async with session_scope() as db:
        user = await get_or_create_user(db, callback.from_user)
        package = await db.get(Package, package_id)
        wallet = await wallet_service.get_or_create_wallet(db, user.id)

        if wallet.balance < total_price:
            await callback.message.answer(
                f"❌ আপনার ব্যালেন্স পর্যাপ্ত নয়। প্রয়োজন: ৳{total_price:.0f}, আছে: ৳{wallet.balance:.0f}",
                reply_markup=insufficient_balance_kb(),
            )
            await callback.answer()
            return

        discount_per_unit = package.selling_price - unit_price
        results = []
        for item in valid:
            try:
                player_name, provider_product, provider = await order_service.validate_uid_for_package(
                    db, package_id=package.id, uid=item["uid"]
                )
                order = await order_service.create_order(
                    db, user=user, package=package, uid=item["uid"], player_name=player_name,
                    provider_product=provider_product, provider=provider,
                    final_price=unit_price, discount_amount=discount_per_unit, vip_discount_percent=vip_discount_percent,
                )
                results.append((item["uid"], order.status.value, order.order_number))
            except AppError as err:
                results.append((item["uid"], "SKIPPED", err.user_message))

    lines = ["🎁 <b>বাল্ক অর্ডার সম্পন্ন</b>\n"]
    for uid, status, extra in results:
        emoji = {"COMPLETED": "🟢", "PROCESSING": "🟡", "PENDING": "🟡", "FAILED": "🔴", "SKIPPED": "⚪️"}.get(status, "⚪️")
        lines.append(f"{emoji} {uid} — {status}" + (f" (#{extra})" if status not in ("SKIPPED",) else f" — {extra}"))

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "bulk_cancel")
async def bulk_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await callback.message.answer("❌ বাল্ক অর্ডার বাতিল করা হয়েছে।", reply_markup=main_menu_kb())
    await callback.answer()

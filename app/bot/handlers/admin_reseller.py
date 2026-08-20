from decimal import Decimal, InvalidOperation
from uuid import UUID

from aiogram import Router, F, Bot
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope
from app.models import ResellerAccount, ResellerApplication, Package, User
from app.services import reseller_service, reseller_application_service
from app.core.exceptions import AppError
from app.bot.states import AdminResellerStates
from app.bot.keyboards import (
    admin_menu_kb, admin_cancel_kb,
    admin_resellers_menu_kb, admin_resellers_list_kb, admin_reseller_detail_kb,
    admin_reseller_pricing_method_kb, admin_reseller_custom_prices_kb, admin_reseller_applications_kb,
    reseller_apply_admin_kb,
)

settings = get_settings()
router = Router(name="admin_reseller")


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.telegram_admin_id_list


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _reseller_text(r: ResellerAccount) -> str:
    pricing = f"Flat {r.flat_discount_percent}%" if r.pricing_method == "FLAT_PERCENT" else "Custom (per package)"
    bound = f"🔗 Telegram ID: {r.telegram_id}" if r.telegram_id else "⚪ কারো সাথে বাঁধা হয়নি"
    return (
        f"🏪 <b>{r.username}</b>\n\n"
        f"{bound}\n"
        f"💲 Pricing: {pricing}\n"
        f"Status: {'🟢 Active' if r.status == 'ACTIVE' else '🔴 Revoked'}"
    )


@router.message(F.text == "🏪 Resellers")
async def resellers_menu(message: Message):
    await message.answer("🏪 <b>Reseller ব্যবস্থাপনা</b>", parse_mode="HTML", reply_markup=admin_resellers_menu_kb())


@router.callback_query(F.data == "res_menu")
async def resellers_menu_cb(callback: CallbackQuery):
    await callback.message.edit_text("🏪 <b>Reseller ব্যবস্থাপনা</b>", parse_mode="HTML", reply_markup=admin_resellers_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "res_list")
async def resellers_list(callback: CallbackQuery):
    async with session_scope() as db:
        resellers = await reseller_service.list_resellers(db)
    await callback.message.edit_text("📋 <b>Reseller List</b>", parse_mode="HTML", reply_markup=admin_resellers_list_kb(resellers))
    await callback.answer()


@router.callback_query(F.data.startswith("res_v:"))
async def reseller_view(callback: CallbackQuery, state: FSMContext):
    reseller_id = callback.data.split(":", 1)[1]
    await state.update_data(admin_reseller_id=reseller_id)
    async with session_scope() as db:
        r = await db.get(ResellerAccount, reseller_id)
    await callback.message.edit_text(_reseller_text(r), parse_mode="HTML", reply_markup=admin_reseller_detail_kb(r))
    await callback.answer()


@router.callback_query(F.data.startswith("res_toggle:"))
async def reseller_toggle(callback: CallbackQuery):
    reseller_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        r = await reseller_service.toggle_status(db, reseller_id=UUID(reseller_id))
    await callback.message.edit_text(_reseller_text(r), parse_mode="HTML", reply_markup=admin_reseller_detail_kb(r))
    await callback.answer("✅ আপডেট হয়েছে")


@router.callback_query(F.data.startswith("res_reset_pw:"))
async def reseller_reset_password_start(callback: CallbackQuery, state: FSMContext):
    reseller_id = callback.data.split(":", 1)[1]
    await state.update_data(admin_reseller_id=reseller_id)
    await state.set_state(AdminResellerStates.waiting_reset_password)
    await callback.message.answer("🔑 নতুন পাসওয়ার্ড লিখুন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminResellerStates.waiting_reset_password, F.text)
async def reseller_reset_password_save(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    async with session_scope() as db:
        r = await reseller_service.reset_password(db, reseller_id=UUID(data["admin_reseller_id"]), new_password=message.text.strip())
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    await message.answer(f"✅ '{r.username}'-এর পাসওয়ার্ড পরিবর্তন হয়েছে।", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("res_pricing:"))
async def reseller_pricing_menu(callback: CallbackQuery):
    reseller_id = callback.data.split(":", 1)[1]
    await callback.message.edit_text("💲 কোন পদ্ধতি ব্যবহার করবেন?", reply_markup=admin_reseller_pricing_method_kb(reseller_id))
    await callback.answer()


@router.callback_query(F.data.startswith("res_pm:"))
async def reseller_pricing_method_selected(callback: CallbackQuery, state: FSMContext):
    _, reseller_id, method = callback.data.split(":", 2)
    await state.update_data(admin_reseller_id=reseller_id)

    if method == "FLAT_PERCENT":
        await state.set_state(AdminResellerStates.waiting_flat_percent)
        await callback.message.answer("সব প্যাকেজে কত শতাংশ ছাড় দেবেন? (যেমন: 10):", reply_markup=admin_cancel_kb())
        await callback.answer()
        return

    async with session_scope() as db:
        await reseller_service.set_pricing_method(db, reseller_id=UUID(reseller_id), pricing_method="CUSTOM")
        packages = (await db.execute(select(Package).where(Package.is_active == True).order_by(Package.sort_order.asc()))).scalars().all()  # noqa: E712
        priced = await reseller_service.list_custom_prices(db, reseller_id=UUID(reseller_id))
    priced_map = {p.package_id: p.custom_price for p in priced}
    await callback.message.edit_text(
        "💲 প্রতিটা প্যাকেজে দাম বসান (যেগুলোতে দাম নেই সেগুলো Reseller-এর কাছে দেখানো হবে না):",
        reply_markup=admin_reseller_custom_prices_kb(packages, priced_map),
    )
    await callback.answer()


@router.message(AdminResellerStates.waiting_flat_percent, F.text)
async def reseller_flat_percent_save(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
        if value < 0 or value > 100:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ ০ থেকে ১০০ এর মধ্যে একটি সংখ্যা দিন।")
        return
    data = await state.get_data()
    await state.clear()
    async with session_scope() as db:
        r = await reseller_service.set_pricing_method(
            db, reseller_id=UUID(data["admin_reseller_id"]), pricing_method="FLAT_PERCENT", flat_discount_percent=value,
        )
    await message.answer(f"✅ '{r.username}'-এর জন্য {value}% flat ছাড় সেট করা হয়েছে।", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "res_cp_back")
async def reseller_custom_price_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    reseller_id = data.get("admin_reseller_id")
    async with session_scope() as db:
        r = await db.get(ResellerAccount, reseller_id)
    await callback.message.edit_text(_reseller_text(r), parse_mode="HTML", reply_markup=admin_reseller_detail_kb(r))
    await callback.answer()


@router.callback_query(F.data.startswith("res_cp:"))
async def reseller_custom_price_pick(callback: CallbackQuery, state: FSMContext):
    package_id = callback.data.split(":", 1)[1]
    await state.update_data(admin_package_id=package_id)
    await state.set_state(AdminResellerStates.waiting_custom_price)
    await callback.message.answer("💲 এই প্যাকেজের জন্য দাম লিখুন (৳):", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminResellerStates.waiting_custom_price, F.text)
async def reseller_custom_price_save(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
        if value <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ ০ এর বেশি একটি সংখ্যা দিন।")
        return

    data = await state.get_data()
    reseller_id, package_id = data["admin_reseller_id"], data["admin_package_id"]
    await state.clear()
    await state.update_data(admin_reseller_id=reseller_id)  # keep reseller context for "back"

    async with session_scope() as db:
        await reseller_service.set_custom_price(db, reseller_id=UUID(reseller_id), package_id=UUID(package_id), price=value)
        packages = (await db.execute(select(Package).where(Package.is_active == True).order_by(Package.sort_order.asc()))).scalars().all()  # noqa: E712
        priced = await reseller_service.list_custom_prices(db, reseller_id=UUID(reseller_id))
    priced_map = {p.package_id: p.custom_price for p in priced}
    await message.answer("✅ দাম সংরক্ষণ হয়েছে।", reply_markup=admin_reseller_custom_prices_kb(packages, priced_map))


# ============================================================== ADD NEW ====
@router.callback_query(F.data == "res_add")
async def reseller_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminResellerStates.waiting_username)
    await callback.message.answer("🆔 নতুন Reseller-এর জন্য একটা ইউজারনেম দিন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminResellerStates.waiting_username, F.text)
async def reseller_add_username(message: Message, state: FSMContext):
    await state.update_data(new_username=message.text.strip())
    await state.set_state(AdminResellerStates.waiting_password)
    await message.answer("🔑 পাসওয়ার্ড দিন:", reply_markup=admin_cancel_kb())


@router.message(AdminResellerStates.waiting_password, F.text)
async def reseller_add_password(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    username, password = data["new_username"], message.text.strip()
    prefill_telegram_id = data.get("apply_telegram_id")  # set when approving an application
    await state.clear()

    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass

    async with session_scope() as db:
        try:
            account = await reseller_service.create_account(
                db, admin_telegram_id=message.from_user.id, username=username, password=password,
                pricing_method="FLAT_PERCENT", flat_discount_percent=Decimal("0"),
                telegram_id=prefill_telegram_id,
            )
        except AppError as err:
            await message.answer(err.user_message, reply_markup=admin_menu_kb())
            return
        uname = account.username

    await message.answer(
        f"✅ Reseller '{uname}' তৈরি হয়েছে (ডিফল্ট: 0% ছাড়)।\nএখন pricing সেট করতে 🏪 Resellers → List → {uname} → 💲 Pricing এ যান।",
        reply_markup=admin_menu_kb(),
    )

    if prefill_telegram_id:
        try:
            await bot.send_message(
                prefill_telegram_id,
                f"🎉 আপনার Reseller আবেদন অনুমোদিত হয়েছে!\n\nইউজারনেম: <code>{uname}</code>\nপাসওয়ার্ড: <code>{password}</code>\n\n"
                f"এখন /start দিয়ে Reseller হিসেবে Login করুন।",
                parse_mode="HTML",
            )
        except Exception:  # noqa: BLE001
            pass


# ============================================================ APPLICATIONS =
@router.callback_query(F.data == "res_apps")
async def applications_list(callback: CallbackQuery):
    async with session_scope() as db:
        apps = await reseller_application_service.list_pending(db)
    await callback.message.edit_text("📝 <b>Pending Applications</b>", parse_mode="HTML", reply_markup=admin_reseller_applications_kb(apps))
    await callback.answer()


@router.callback_query(F.data.startswith("resapp_v:"))
async def application_view(callback: CallbackQuery):
    app_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        app_row = await db.get(ResellerApplication, app_id)
        user = await db.get(User, app_row.user_id) if app_row else None
    if app_row is None:
        await callback.answer("❌ আবেদন খুঁজে পাওয়া যায়নি।", show_alert=True)
        return
    uname = f"@{user.telegram_username}" if user and user.telegram_username else f"ID {app_row.telegram_id}"
    await callback.message.edit_text(
        f"📝 <b>Reseller আবেদন</b>\n\nফ্রম: {uname}\nবার্তা: {app_row.message or '-'}",
        parse_mode="HTML", reply_markup=reseller_apply_admin_kb(app_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("resapp_approve:"))
async def application_approve(callback: CallbackQuery, state: FSMContext):
    app_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        app_row = await reseller_application_service.mark_approved(db, application_id=UUID(app_id), admin_telegram_id=callback.from_user.id)
        telegram_id = app_row.telegram_id

    await state.update_data(apply_telegram_id=telegram_id)
    await state.set_state(AdminResellerStates.waiting_username)
    await callback.message.answer(
        f"✅ আবেদন Approved। এখন এই ইউজারের (Telegram ID: {telegram_id}) জন্য একটা ইউজারনেম দিন:",
        reply_markup=admin_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("resapp_reject:"))
async def application_reject(callback: CallbackQuery, bot: Bot):
    app_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        app_row = await reseller_application_service.mark_rejected(db, application_id=UUID(app_id), admin_telegram_id=callback.from_user.id)
        telegram_id = app_row.telegram_id

    await callback.message.edit_text("❌ আবেদনটি Reject করা হয়েছে।")
    await callback.answer("❌ Rejected")
    try:
        await bot.send_message(telegram_id, "❌ দুঃখিত, আপনার Reseller আবেদনটি এই মুহূর্তে গ্রহণ করা যায়নি।")
    except Exception:  # noqa: BLE001
        pass

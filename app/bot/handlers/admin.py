"""
The entire Admin Panel lives inside the Telegram bot now (no separate website).
Access control: only Telegram accounts whose numeric ID is listed in
settings.TELEGRAM_ADMIN_IDS ever match this router (see AdminFilter below) --
everyone else's messages fall through untouched to the normal user handlers.
"""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from aiogram import Router, F
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from sqlalchemy import select, func, desc, or_

from app.config import get_settings
from app.database import session_scope
from app.models import (
    User, Wallet, Order, OrderStatus, OrderLog, Deposit, DepositStatus, PaymentMethod,
    ApiProvider, Package, ProviderProduct, Referral, AdminLog, WalletTransaction,
    TransactionType, TransactionDirection,
)
from app.services import (
    wallet_service, provider_service, deposit_service, order_service, broadcast_service,
    fraud_service, analytics_service, export_service,
)
from app.services.settings_service import get_setting, upsert_setting
from app.core.security import encrypt_secret
from app.core.exceptions import AppError
from app.bot.states import (
    AdminAddProviderStates, AdminEditProviderStates, AdminAddPackageStates, AdminAdjustBalanceStates,
    AdminBroadcastStates, AdminAddPaymentMethodStates, AdminSettingsStates,
)
from app.bot.keyboards import (
    admin_menu_kb, admin_cancel_kb, main_menu_kb,
    admin_providers_list_kb, admin_provider_detail_kb, admin_provider_code_kb,
    admin_provider_delete_confirm_kb, admin_provider_edit_field_kb,
    admin_packages_list_kb, admin_package_detail_kb, admin_package_provider_select_kb,
    admin_orders_status_filter_kb, admin_order_actions_kb,
    admin_deposit_actions_kb, admin_user_actions_kb, admin_balance_direction_kb,
    admin_broadcast_target_kb, admin_settings_menu_kb, admin_payment_methods_kb,
    admin_broadcast_schedule_choice_kb, admin_scheduled_broadcasts_list_kb,
    dashboard_extra_kb, admin_export_menu_kb,
)

settings = get_settings()
router = Router(name="admin")


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.telegram_admin_id_list


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


STATUS_EMOJI = {"PENDING": "🟡", "PROCESSING": "🟡", "COMPLETED": "🟢", "FAILED": "🔴", "CANCELED": "⚪️"}


# ============================================================ ENTRY POINT ==
@router.message(Command("admin"))
async def admin_entry(message: Message):
    await message.answer("👑 <b>Admin Panel</b>\n\nনিচের মেনু থেকে বেছে নিন 👇", reply_markup=admin_menu_kb(), parse_mode="HTML")


@router.message(F.text == "🔙 User মেনুতে ফিরুন")
async def back_to_user_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("প্রধান মেনু 👇", reply_markup=main_menu_kb())


@router.message(F.text == "❌ বাতিল")
async def admin_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ বাতিল করা হয়েছে।", reply_markup=admin_menu_kb())


# =============================================================== DASHBOARD =
@router.message(F.text == "📊 Dashboard")
async def admin_dashboard(message: Message):
    async with session_scope() as db:
        total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
        active_users = (await db.execute(select(func.count()).select_from(User).where(User.is_banned == False))).scalar() or 0  # noqa: E712
        total_deposits = (await db.execute(select(func.coalesce(func.sum(Deposit.amount), 0)).where(Deposit.status == DepositStatus.APPROVED))).scalar() or Decimal("0")
        total_sales = (await db.execute(select(func.coalesce(func.sum(Order.selling_price), 0)).where(Order.status == OrderStatus.COMPLETED))).scalar() or Decimal("0")
        total_cost = (await db.execute(select(func.coalesce(func.sum(Order.provider_cost_snapshot), 0)).where(Order.status == OrderStatus.COMPLETED))).scalar() or Decimal("0")
        total_orders = (await db.execute(select(func.count()).select_from(Order))).scalar() or 0
        pending_orders = (await db.execute(select(func.count()).select_from(Order).where(Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING])))).scalar() or 0
        pending_deposits = (await db.execute(select(func.count()).select_from(Deposit).where(Deposit.status == DepositStatus.PENDING))).scalar() or 0
        failed_orders = (await db.execute(select(func.count()).select_from(Order).where(Order.status == OrderStatus.FAILED))).scalar() or 0
        providers = (await db.execute(select(ApiProvider).order_by(ApiProvider.priority.asc()))).scalars().all()

    provider_lines = "\n".join(f"  {'🟢' if p.is_active else '🔴'} {p.name}" for p in providers) or "  (কোনো provider নেই)"

    text = (
        "📊 <b>Dashboard</b>\n\n"
        f"👥 Total Users: {total_users}\n"
        f"🟢 Active Users: {active_users}\n"
        f"💰 Total Deposits: ৳{total_deposits:.0f}\n"
        f"💎 Total Sales: ৳{total_sales:.0f}\n"
        f"📈 Total Profit: ৳{(total_sales - total_cost):.0f}\n"
        f"📦 Total Orders: {total_orders}\n"
        f"⏳ Pending Orders: {pending_orders}\n"
        f"❌ Failed Orders: {failed_orders}\n"
        f"💳 Pending Deposits: {pending_deposits}\n\n"
        f"🔌 <b>Providers</b>\n{provider_lines}"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=dashboard_extra_kb())


@router.callback_query(F.data == "admin_dashboard_chart")
async def admin_dashboard_chart(callback: CallbackQuery):
    async with session_scope() as db:
        rows = await analytics_service.daily_sales(db, days=7)
        breakdown = await analytics_service.order_status_breakdown(db, days=30)
        top = await analytics_service.top_packages(db, days=30, limit=5)
        stats = await analytics_service.summary_stats(db, days=30)

    chart = analytics_service.render_ascii_bar_chart(rows)
    status_lines = "\n".join(f"  {k}: {v}" for k, v in breakdown.items()) or "  (কোনো ডেটা নেই)"
    top_lines = "\n".join(f"  {i+1}. {name} — {count}টি (৳{rev:.0f})" for i, (name, count, rev) in enumerate(top)) or "  (কোনো ডেটা নেই)"

    text = (
        "📈 <b>গত ৭ দিনের বিক্রয় (৳)</b>\n\n"
        f"<pre>{chart}</pre>\n\n"
        "📊 <b>গত ৩০ দিনের সামারি</b>\n"
        f"👥 নতুন ইউজার: {stats['new_users']}\n"
        f"💰 রেভিনিউ: ৳{stats['revenue']:.0f}\n"
        f"📦 সম্পন্ন অর্ডার: {stats['completed_orders']}\n"
        f"💳 ডিপোজিট: ৳{stats['deposits_total']:.0f}\n"
        f"📊 গড় অর্ডার মূল্য: ৳{stats['avg_order_value']:.0f}\n\n"
        f"🗂️ <b>অর্ডার স্ট্যাটাস (৩০ দিন)</b>\n{status_lines}\n\n"
        f"🏆 <b>টপ প্যাকেজ (৩০ দিন)</b>\n{top_lines}"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_dashboard_export")
async def admin_dashboard_export_menu(callback: CallbackQuery):
    await callback.message.answer("📤 কোনটা Export করতে চান?", reply_markup=admin_export_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_export:"))
async def admin_export_run(callback: CallbackQuery):
    _, kind, period = callback.data.split(":", 2)
    days = None if period == "all" else int(period)

    async with session_scope() as db:
        if kind == "orders":
            buf = await export_service.orders_to_csv(db, days=days)
            filename = f"orders_{period}.csv"
        else:
            buf = await export_service.deposits_to_csv(db, days=days)
            filename = f"deposits_{period}.csv"

    await callback.message.answer_document(
        BufferedInputFile(buf.read(), filename=filename), caption=f"📤 Export: {kind} ({period})",
    )
    await callback.answer()


# =============================================================== PROVIDERS =
@router.message(F.text == "🔌 Providers")
async def admin_providers_menu(message: Message):
    async with session_scope() as db:
        providers = (await db.execute(select(ApiProvider).order_by(ApiProvider.priority.asc()))).scalars().all()
    if not providers:
        await message.answer("এখনো কোনো Provider নেই।", reply_markup=None)
    await message.answer("🔌 <b>API Providers</b>", parse_mode="HTML", reply_markup=admin_providers_list_kb(providers))


@router.callback_query(F.data == "admin_provider_list")
async def admin_provider_list_cb(callback: CallbackQuery):
    async with session_scope() as db:
        providers = (await db.execute(select(ApiProvider).order_by(ApiProvider.priority.asc()))).scalars().all()
    await callback.message.edit_text("🔌 <b>API Providers</b>", parse_mode="HTML", reply_markup=admin_providers_list_kb(providers))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_provider_view:"))
async def admin_provider_view(callback: CallbackQuery):
    provider_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        provider = await db.get(ApiProvider, provider_id)
        masked = provider_service.masked_api_key(provider)
    text = (
        f"🔌 <b>{provider.name}</b>\n\n"
        f"Code: <code>{provider.code}</code>\n"
        f"Base URL: {provider.base_url}\n"
        f"API Key: <code>{masked}</code>\n"
        f"Priority: {provider.priority}\n"
        f"Status: {'🟢 Active' if provider.is_active else '🔴 Inactive'}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_provider_detail_kb(provider))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_provider_toggle:"))
async def admin_provider_toggle(callback: CallbackQuery):
    provider_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        provider = await provider_service.toggle_provider(db, provider_id=UUID(provider_id), admin_telegram_id=callback.from_user.id)
        masked = provider_service.masked_api_key(provider)
    text = (
        f"🔌 <b>{provider.name}</b>\n\nCode: <code>{provider.code}</code>\nBase URL: {provider.base_url}\n"
        f"API Key: <code>{masked}</code>\nPriority: {provider.priority}\n"
        f"Status: {'🟢 Active' if provider.is_active else '🔴 Inactive'}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_provider_detail_kb(provider))
    await callback.answer("✅ আপডেট হয়েছে")


@router.callback_query(F.data.startswith("admin_provider_test:"))
async def admin_provider_test(callback: CallbackQuery):
    provider_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        result = await provider_service.test_provider_connection(db, provider_id=UUID(provider_id))
    if result["ok"]:
        secret = result.get("webhook_secret")
        masked_secret = (secret[:4] + "…" + secret[-4:]) if secret and len(secret) > 8 else (secret or "N/A")
        detail = (
            "✅ <b>কানেকশন সফল</b>\n\n"
            f"User ID: <code>{result.get('user_id', 'N/A')}</code>\n"
            f"Username: <code>{result.get('username', 'N/A')}</code>\n"
            f"Balance: <b>{result['balance']} {result.get('currency', '')}</b>\n"
            f"Webhook Secret: <code>{masked_secret}</code>"
        )
        await callback.message.answer(detail, parse_mode="HTML")
        await callback.answer(f"✅ Balance: {result['balance']} {result.get('currency', '')}")
    else:
        await callback.answer(f"❌ ব্যর্থ: {result['error'][:150]}", show_alert=True)


_EDIT_FIELD_MAP = {
    "nm": "name", "url": "base_url", "key": "api_key",
    "val": "validation_endpoint", "ord": "order_endpoint",
    "sts": "status_endpoint", "bal": "balance_endpoint", "pri": "priority",
}
_EDIT_FIELD_LABELS = {
    "nm": "Name", "url": "Base URL", "key": "API Key",
    "val": "Validation Endpoint", "ord": "Order Endpoint",
    "sts": "Status Endpoint", "bal": "Balance Endpoint", "pri": "Priority",
}


@router.callback_query(F.data.startswith("ap_delc:"))
async def admin_provider_delete_confirm(callback: CallbackQuery):
    provider_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        provider = await db.get(ApiProvider, provider_id)
    await callback.message.edit_text(
        f"⚠️ তুমি কি নিশ্চিত '{provider.name}' Provider-টা <b>স্থায়ীভাবে মুছে ফেলতে</b> চাও?\n"
        f"এর সাথে যুক্ত package-mapping গুলোও প্রভাবিত হতে পারে।",
        parse_mode="HTML", reply_markup=admin_provider_delete_confirm_kb(provider_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ap_del:"))
async def admin_provider_delete(callback: CallbackQuery):
    provider_id = callback.data.split(":", 1)[1]
    try:
        async with session_scope() as db:
            name = await provider_service.delete_provider(db, provider_id=UUID(provider_id), admin_telegram_id=callback.from_user.id)
        async with session_scope() as db:
            providers = (await db.execute(select(ApiProvider).order_by(ApiProvider.priority.asc()))).scalars().all()
        await callback.message.edit_text(
            f"🗑️ Provider '{name}' মুছে ফেলা হয়েছে।\n\n🔌 <b>API Providers</b>",
            parse_mode="HTML", reply_markup=admin_providers_list_kb(providers),
        )
        await callback.answer("✅ Deleted")
    except Exception:
        await callback.answer("❌ Delete ব্যর্থ: এই provider-এর সাথে অন্য ডেটা (যেমন package/order) যুক্ত থাকতে পারে।", show_alert=True)


@router.callback_query(F.data.startswith("ap_edit:"))
async def admin_provider_edit_menu(callback: CallbackQuery):
    provider_id = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        "✏️ কোন ফিল্ড পরিবর্তন করতে চাও?", reply_markup=admin_provider_edit_field_kb(provider_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ap_ef:"))
async def admin_provider_editfield_start(callback: CallbackQuery, state: FSMContext):
    _, provider_id, code = callback.data.split(":", 2)
    field = _EDIT_FIELD_MAP.get(code, code)
    await state.set_state(AdminEditProviderStates.value)
    await state.update_data(provider_id=provider_id, field=field)
    await callback.message.answer(f"নতুন মান লিখুন ({_EDIT_FIELD_LABELS.get(code, code)}):", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminEditProviderStates.value, F.text)
async def admin_provider_editfield_save(message: Message, state: FSMContext):
    data = await state.get_data()
    provider_id, field = data["provider_id"], data["field"]
    await state.clear()
    value = message.text.strip()
    try:
        async with session_scope() as db:
            provider = await provider_service.update_provider_field(
                db, provider_id=UUID(provider_id), admin_telegram_id=message.from_user.id, field=field, value=value,
            )
            masked = provider_service.masked_api_key(provider)
        text = (
            f"✅ আপডেট হয়েছে।\n\n🔌 <b>{provider.name}</b>\n\nCode: <code>{provider.code}</code>\n"
            f"Base URL: {provider.base_url}\nAPI Key: <code>{masked}</code>\nPriority: {provider.priority}\n"
            f"Status: {'🟢 Active' if provider.is_active else '🔴 Inactive'}"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=admin_provider_detail_kb(provider))
    except AppError as e:
        await message.answer(f"❌ আপডেট ব্যর্থ: {e.user_message}", reply_markup=admin_menu_kb())
    except Exception:
        await message.answer("❌ আপডেট ব্যর্থ — মানটা ঠিক আছে কিনা চেক করো।", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_provider_add")
async def admin_provider_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddProviderStates.name)
    await callback.message.answer("🔌 Provider Name লিখুন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminAddProviderStates.name, F.text)
async def admin_provider_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddProviderStates.code)
    await message.answer("Adapter Code বেছে নিন:", reply_markup=admin_provider_code_kb(provider_service.available_provider_codes()))


@router.callback_query(AdminAddProviderStates.code, F.data.startswith("admin_provider_code:"))
async def admin_provider_add_code(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    await state.update_data(code=code)
    await state.set_state(AdminAddProviderStates.base_url)
    default = "https://www.epinby.com/api/v1" if code == "epinby" else ""
    await callback.message.answer(f"Base URL লিখুন (ডিফল্ট: {default}):", reply_markup=admin_cancel_kb())
    await state.update_data(default_base_url=default)
    await callback.answer()


@router.message(AdminAddProviderStates.base_url, F.text)
async def admin_provider_add_base_url(message: Message, state: FSMContext):
    data = await state.get_data()
    value = message.text.strip()
    await state.update_data(base_url=value if value != "-" else data.get("default_base_url", ""))
    await state.set_state(AdminAddProviderStates.api_key)
    await message.answer("API Key লিখুন:")


@router.message(AdminAddProviderStates.api_key, F.text)
async def admin_provider_add_api_key(message: Message, state: FSMContext):
    await state.update_data(api_key=message.text.strip())
    await state.set_state(AdminAddProviderStates.validation_endpoint)
    await message.answer("Validation Endpoint (ডিফল্ট রাখতে - পাঠান, যেমন: /validate-player):")


@router.message(AdminAddProviderStates.validation_endpoint, F.text)
async def admin_provider_add_validation(message: Message, state: FSMContext):
    v = message.text.strip()
    await state.update_data(validation_endpoint=None if v == "-" else v)
    await state.set_state(AdminAddProviderStates.order_endpoint)
    await message.answer("Order Endpoint (ডিফল্ট: -):")


@router.message(AdminAddProviderStates.order_endpoint, F.text)
async def admin_provider_add_order(message: Message, state: FSMContext):
    v = message.text.strip()
    await state.update_data(order_endpoint=None if v == "-" else v)
    await state.set_state(AdminAddProviderStates.status_endpoint)
    await message.answer("Status Endpoint (ডিফল্ট: -), e.g. /order/{id}:")


@router.message(AdminAddProviderStates.status_endpoint, F.text)
async def admin_provider_add_status(message: Message, state: FSMContext):
    v = message.text.strip()
    await state.update_data(status_endpoint=None if v == "-" else v)
    await state.set_state(AdminAddProviderStates.balance_endpoint)
    await message.answer("Balance Endpoint (ডিফল্ট: -):")


@router.message(AdminAddProviderStates.balance_endpoint, F.text)
async def admin_provider_add_balance(message: Message, state: FSMContext):
    v = message.text.strip()
    await state.update_data(balance_endpoint=None if v == "-" else v)
    await state.set_state(AdminAddProviderStates.priority)
    await message.answer("Priority সংখ্যা লিখুন (কম = বেশি অগ্রাধিকার, ডিফল্ট 100 এর জন্য -):")


@router.message(AdminAddProviderStates.priority, F.text)
async def admin_provider_add_priority(message: Message, state: FSMContext):
    v = message.text.strip()
    priority = 100 if v == "-" else int(v) if v.isdigit() else 100
    data = await state.get_data()
    await state.clear()

    try:
        async with session_scope() as db:
            provider = await provider_service.create_provider(
                db, admin_telegram_id=message.from_user.id, name=data["name"], code=data["code"],
                base_url=data["base_url"], api_key=data["api_key"],
                validation_endpoint=data.get("validation_endpoint"), order_endpoint=data.get("order_endpoint"),
                status_endpoint=data.get("status_endpoint"), balance_endpoint=data.get("balance_endpoint"),
                priority=priority, is_active=True,
            )
        await message.answer(f"✅ Provider '{provider.name}' যোগ করা হয়েছে।", reply_markup=admin_menu_kb())
    except AppError as e:
        await message.answer(f"❌ Provider যোগ করা যায়নি: {e.user_message}", reply_markup=admin_menu_kb())
    except Exception:
        await message.answer(
            "❌ Provider যোগ করা যায়নি — সম্ভবত এই নামে বা কোডে (code) আগে থেকেই একটা provider আছে। "
            "আগে পুরনোটা 🔌 Providers থেকে খুলে Delete করে আবার চেষ্টা করুন।",
            reply_markup=admin_menu_kb(),
        )


# ================================================================ PACKAGES =
@router.message(F.text == "📦 Packages")
async def admin_packages_menu(message: Message):
    async with session_scope() as db:
        packages = (await db.execute(select(Package).order_by(Package.sort_order.asc()))).scalars().all()
    await message.answer("📦 <b>Packages</b>", parse_mode="HTML", reply_markup=admin_packages_list_kb(packages))


@router.callback_query(F.data == "admin_package_list")
async def admin_package_list_cb(callback: CallbackQuery):
    async with session_scope() as db:
        packages = (await db.execute(select(Package).order_by(Package.sort_order.asc()))).scalars().all()
    await callback.message.edit_text("📦 <b>Packages</b>", parse_mode="HTML", reply_markup=admin_packages_list_kb(packages))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_package_view:"))
async def admin_package_view(callback: CallbackQuery):
    package_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        package = await db.get(Package, package_id)
        pp = (await db.execute(select(ProviderProduct).where(ProviderProduct.package_id == package_id, ProviderProduct.is_active == True))).scalars().first()  # noqa: E712
    cost_line = f"Provider Cost: ৳{pp.provider_cost:.0f}\nProfit: ৳{(package.selling_price - pp.provider_cost):.0f}" if pp else "Provider Cost: -"
    text = (
        f"📦 <b>{package.name}</b>\n\n"
        f"💎 Diamonds: {package.diamond_amount}\n"
        f"💰 Selling Price: ৳{package.selling_price:.0f}\n"
        f"{cost_line}\n"
        f"Status: {'🟢 Active' if package.is_active else '🔴 Inactive'}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_package_detail_kb(package))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_package_toggle:"))
async def admin_package_toggle(callback: CallbackQuery):
    package_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        package = await db.get(Package, package_id)
        package.is_active = not package.is_active
        db.add(AdminLog(admin_telegram_id=callback.from_user.id, action="TOGGLE_PACKAGE",
                         target_type="package", target_id=str(package.id), new_value={"is_active": package.is_active}))
    await callback.answer("✅ আপডেট হয়েছে")
    await admin_package_view(callback)


@router.callback_query(F.data == "admin_package_add")
async def admin_package_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddPackageStates.name)
    await callback.message.answer("📦 Package Name লিখুন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminAddPackageStates.name, F.text)
async def admin_package_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddPackageStates.diamond_amount)
    await message.answer("💎 Diamond Amount (সংখ্যা):")


@router.message(AdminAddPackageStates.diamond_amount, F.text)
async def admin_package_add_diamonds(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ সংখ্যা লিখুন।")
        return
    await state.update_data(diamond_amount=int(message.text.strip()))
    await state.set_state(AdminAddPackageStates.selling_price)
    await message.answer("💰 Selling Price (৳):")


@router.message(AdminAddPackageStates.selling_price, F.text)
async def admin_package_add_price(message: Message, state: FSMContext):
    try:
        price = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("❌ সঠিক মূল্য লিখুন।")
        return
    await state.update_data(selling_price=str(price))
    async with session_scope() as db:
        providers = (await db.execute(select(ApiProvider).where(ApiProvider.is_active == True))).scalars().all()  # noqa: E712
    if not providers:
        await state.clear()
        await message.answer("⚠️ আগে অন্তত একটি Provider যোগ করুন।", reply_markup=admin_menu_kb())
        return
    await state.set_state(AdminAddPackageStates.provider_select)
    await message.answer("Provider বেছে নিন:", reply_markup=admin_package_provider_select_kb(providers))


@router.callback_query(AdminAddPackageStates.provider_select, F.data.startswith("admin_package_provider:"))
async def admin_package_add_provider(callback: CallbackQuery, state: FSMContext):
    provider_id = callback.data.split(":", 1)[1]
    await state.update_data(provider_id=provider_id)
    await state.set_state(AdminAddPackageStates.provider_product_id)
    await callback.message.answer("Provider Product ID লিখুন (যেমন: 91):")
    await callback.answer()


@router.message(AdminAddPackageStates.provider_product_id, F.text)
async def admin_package_add_product_id(message: Message, state: FSMContext):
    await state.update_data(provider_product_id=message.text.strip())
    await state.set_state(AdminAddPackageStates.provider_cost)
    await message.answer("Provider Cost (৳):")


@router.message(AdminAddPackageStates.provider_cost, F.text)
async def admin_package_add_cost(message: Message, state: FSMContext):
    try:
        cost = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("❌ সঠিক মূল্য লিখুন।")
        return
    data = await state.get_data()
    await state.clear()

    async with session_scope() as db:
        package = Package(
            name=data["name"], diamond_amount=data["diamond_amount"],
            selling_price=Decimal(data["selling_price"]), primary_provider_id=UUID(data["provider_id"]),
            is_active=True,
        )
        db.add(package)
        await db.flush()
        db.add(ProviderProduct(
            provider_id=UUID(data["provider_id"]), package_id=package.id,
            provider_product_id=data["provider_product_id"], provider_cost=cost, is_active=True,
        ))
        db.add(AdminLog(admin_telegram_id=message.from_user.id, action="CREATE_PACKAGE",
                         target_type="package", target_id=str(package.id), new_value={"name": data["name"]}))

    await message.answer(f"✅ Package '{data['name']}' যোগ করা হয়েছে।", reply_markup=admin_menu_kb())


# ================================================================== ORDERS =
@router.message(F.text == "🛒 Orders")
async def admin_orders_menu(message: Message):
    async with session_scope() as db:
        orders = (await db.execute(select(Order).order_by(desc(Order.created_at)).limit(10))).scalars().all()
    if not orders:
        await message.answer("📭 কোনো অর্ডার নেই।")
        return
    for o in orders:
        emoji = STATUS_EMOJI.get(o.status.value, "🟡")
        text = (
            f"📦 {o.order_number}\n💎 {o.product_name_snapshot}\n🆔 {o.game_uid}\n"
            f"💰 ৳{o.selling_price:.0f}\n{emoji} {o.status.value}"
        )
        await message.answer(text, reply_markup=admin_order_actions_kb(o))
    await message.answer("🔎 স্ট্যাটাস অনুযায়ী ফিল্টার করতে চান?", reply_markup=admin_orders_status_filter_kb())


@router.callback_query(F.data.startswith("admin_orders_filter:"))
async def admin_orders_filter(callback: CallbackQuery):
    status = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        orders = (await db.execute(
            select(Order).where(Order.status == OrderStatus(status)).order_by(desc(Order.created_at)).limit(15)
        )).scalars().all()
    await callback.answer()
    if not orders:
        await callback.message.answer(f"📭 {status} স্ট্যাটাসে কোনো অর্ডার নেই।")
        return
    for o in orders:
        emoji = STATUS_EMOJI.get(o.status.value, "🟡")
        text = f"📦 {o.order_number}\n💎 {o.product_name_snapshot}\n🆔 {o.game_uid}\n💰 ৳{o.selling_price:.0f}\n{emoji} {o.status.value}"
        await callback.message.answer(text, reply_markup=admin_order_actions_kb(o))


@router.callback_query(F.data.startswith("admin_order_retry:"))
async def admin_order_retry(callback: CallbackQuery):
    order_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        try:
            new_order = await order_service.retry_failed_order(db, order_id=UUID(order_id), admin_telegram_id=callback.from_user.id)
        except AppError as err:
            await callback.answer(err.user_message, show_alert=True)
            return
    if new_order:
        await callback.answer("🔄 নতুন অর্ডার তৈরি হয়েছে")
        await callback.message.answer(f"✅ Retry successful.\n📦 নতুন Order: {new_order.order_number}\nStatus: {new_order.status.value}")
    else:
        await callback.answer("❌ Retry ব্যর্থ হয়েছে", show_alert=True)


# ================================================================ DEPOSITS =
@router.message(F.text == "💳 Deposits")
async def admin_deposits_menu(message: Message):
    async with session_scope() as db:
        deposits = (await db.execute(
            select(Deposit).where(Deposit.status == DepositStatus.PENDING).order_by(desc(Deposit.created_at)).limit(15)
        )).scalars().all()
        methods = {m.id: m.name for m in (await db.execute(select(PaymentMethod))).scalars().all()}

    if not deposits:
        await message.answer("📭 কোনো Pending ডিপোজিট নেই।")
        return

    for d in deposits:
        text = (
            f"🧾 {d.deposit_number}\n💳 {methods.get(d.payment_method_id, '-')}\n"
            f"💰 ৳{d.amount:.2f}\nRef: {d.transaction_reference}"
            + (f" · {d.sender_number}" if d.sender_number else "")
        )
        await message.answer(text, reply_markup=admin_deposit_actions_kb(d.id))


@router.callback_query(F.data.startswith("admin_deposit_approve:"))
async def admin_deposit_approve(callback: CallbackQuery):
    deposit_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        try:
            await deposit_service.approve_deposit(db, deposit_id=UUID(deposit_id), admin_telegram_id=callback.from_user.id)
        except AppError as err:
            await callback.answer(err.user_message, show_alert=True)
            return
    await callback.message.edit_text(callback.message.text + "\n\n✅ Approved")
    await callback.answer("✅ Approved")


@router.callback_query(F.data.startswith("admin_deposit_reject:"))
async def admin_deposit_reject(callback: CallbackQuery):
    deposit_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        try:
            deposit, newly_flagged = await deposit_service.reject_deposit(
                db, deposit_id=UUID(deposit_id), admin_telegram_id=callback.from_user.id, reason="Rejected by admin",
            )
        except AppError as err:
            await callback.answer(err.user_message, show_alert=True)
            return
        flag_reason, flagged_user_label = None, None
        if newly_flagged:
            user = await db.get(User, deposit.user_id)
            flag_reason = user.flag_reason
            flagged_user_label = f"@{user.telegram_username}" if user.telegram_username else f"ID {user.telegram_id}"
    await callback.message.edit_text(callback.message.text + "\n\n❌ Rejected")
    await callback.answer("❌ Rejected")
    if newly_flagged:
        await callback.message.answer(
            f"🚩 <b>সন্দেহজনক কার্যকলাপ সনাক্ত হয়েছে</b>\n\nইউজার {flagged_user_label} স্বয়ংক্রিয়ভাবে ফ্ল্যাগ করা হয়েছে।\nকারণ: {flag_reason}\n\n👥 Users থেকে বিস্তারিত দেখুন।",
            parse_mode="HTML",
        )


# =================================================================== USERS =
@router.message(F.text == "👥 Users")
async def admin_users_menu(message: Message, state: FSMContext):
    await state.set_state(AdminAdjustBalanceStates.waiting_user_lookup)
    await message.answer("🔍 Telegram ID অথবা ইউজারনেম পাঠান:", reply_markup=admin_cancel_kb())


@router.message(AdminAdjustBalanceStates.waiting_user_lookup, F.text)
async def admin_users_lookup(message: Message, state: FSMContext):
    q = message.text.strip().lstrip("@")
    async with session_scope() as db:
        stmt = select(User)
        if q.isdigit():
            stmt = stmt.where(User.telegram_id == int(q))
        else:
            stmt = stmt.where(or_(User.telegram_username.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
        user = (await db.execute(stmt.limit(1))).scalar_one_or_none()

        if user is None:
            await message.answer("❌ ইউজার পাওয়া যায়নি।")
            return

        wallet = await wallet_service.get_or_create_wallet(db, user.id)
        total_orders = (await db.execute(select(func.count()).select_from(Order).where(Order.user_id == user.id))).scalar() or 0
        referral_count = (await db.execute(select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id))).scalar() or 0

    await state.clear()
    await state.update_data(target_user_id=str(user.id))

    text = (
        f"👤 <b>{user.full_name or '-'}</b> (@{user.telegram_username or '-'})\n\n"
        f"Telegram ID: <code>{user.telegram_id}</code>\n"
        f"💰 Balance: ৳{wallet.balance:.2f}\n"
        f"➕ Deposit: ৳{wallet.total_deposit:.2f}\n"
        f"💎 Purchase: ৳{wallet.total_purchase:.2f}\n"
        f"📦 Orders: {total_orders}\n"
        f"🎁 Referrals: {referral_count}\n"
        f"Status: {'🚫 Banned' if user.is_banned else '🟢 Active'}"
    )
    if user.is_flagged:
        text += f"\n🚩 <b>Flagged:</b> {user.flag_reason or 'সন্দেহজনক কার্যকলাপ'}"
    await message.answer(text, parse_mode="HTML", reply_markup=admin_user_actions_kb(user))


@router.callback_query(F.data.startswith("admin_user_ban_toggle:"))
async def admin_user_ban_toggle(callback: CallbackQuery):
    user_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        user = await db.get(User, user_id)
        user.is_banned = not user.is_banned
        db.add(AdminLog(admin_telegram_id=callback.from_user.id, action="BAN_TOGGLE_USER",
                         target_type="user", target_id=str(user.id), new_value={"is_banned": user.is_banned}))
    await callback.answer("✅ আপডেট হয়েছে")
    await callback.message.answer(f"{'🚫 Banned' if user.is_banned else '✅ Unbanned'}")


@router.callback_query(F.data.startswith("admin_user_unflag:"))
async def admin_user_unflag(callback: CallbackQuery):
    user_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        await fraud_service.unflag_user(db, user_id=UUID(user_id))
        db.add(AdminLog(admin_telegram_id=callback.from_user.id, action="UNFLAG_USER", target_type="user", target_id=user_id))
    await callback.answer("✅ Unflagged")
    await callback.message.answer("🚩 Flag সরিয়ে ফেলা হয়েছে।")


@router.message(F.text == "🚩 Flagged Users")
async def admin_flagged_users(message: Message):
    async with session_scope() as db:
        users = await fraud_service.list_flagged_users(db)
    if not users:
        await message.answer("✅ কোনো flagged ইউজার নেই।")
        return
    lines = ["🚩 <b>Flagged Users</b>\n"]
    for u in users:
        label = f"@{u.telegram_username}" if u.telegram_username else f"ID {u.telegram_id}"
        lines.append(f"• {label} — {u.flag_reason or '-'}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_user_adjust:"))
async def admin_user_adjust_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.data.split(":", 1)[1]
    await state.update_data(target_user_id=user_id)
    await callback.message.answer("দিক বেছে নিন:", reply_markup=admin_balance_direction_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_balance_dir:"))
async def admin_user_adjust_direction(callback: CallbackQuery, state: FSMContext):
    direction = callback.data.split(":", 1)[1]
    await state.update_data(direction=direction)
    await state.set_state(AdminAdjustBalanceStates.waiting_amount)
    await callback.message.answer("💰 পরিমাণ লিখুন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminAdjustBalanceStates.waiting_amount, F.text)
async def admin_user_adjust_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ সঠিক পরিমাণ লিখুন।")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(AdminAdjustBalanceStates.waiting_reason)
    await message.answer("📝 কারণ লিখুন (মাস্ট):")


@router.message(AdminAdjustBalanceStates.waiting_reason, F.text)
async def admin_user_adjust_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    reason = message.text.strip()
    await state.clear()

    async with session_scope() as db:
        try:
            if data["direction"] == "credit":
                await wallet_service.credit_wallet(
                    db, user_id=UUID(data["target_user_id"]), amount=Decimal(data["amount"]),
                    txn_type=TransactionType.ADMIN_ADJUSTMENT, reference_type="admin",
                    reference_id=str(message.from_user.id), note=reason,
                    created_by_admin_telegram_id=message.from_user.id,
                )
            else:
                await wallet_service.debit_wallet(
                    db, user_id=UUID(data["target_user_id"]), amount=Decimal(data["amount"]),
                    txn_type=TransactionType.ADMIN_ADJUSTMENT, reference_type="admin",
                    reference_id=str(message.from_user.id), note=reason,
                    created_by_admin_telegram_id=message.from_user.id,
                )
            db.add(AdminLog(admin_telegram_id=message.from_user.id, action="ADJUST_BALANCE",
                             target_type="user", target_id=data["target_user_id"],
                             new_value={"direction": data["direction"], "amount": data["amount"], "reason": reason}))
        except AppError as err:
            await message.answer(err.user_message, reply_markup=admin_menu_kb())
            return

    await message.answer("✅ ব্যালেন্স আপডেট করা হয়েছে।", reply_markup=admin_menu_kb())


# ================================================================= FINANCE =
@router.message(F.text == "💰 Finance")
async def admin_finance(message: Message):
    async with session_scope() as db:
        total_deposits = (await db.execute(select(func.coalesce(func.sum(Deposit.amount), 0)).where(Deposit.status == DepositStatus.APPROVED))).scalar() or Decimal("0")
        total_sales = (await db.execute(select(func.coalesce(func.sum(Order.selling_price), 0)).where(Order.status == OrderStatus.COMPLETED))).scalar() or Decimal("0")
        total_cost = (await db.execute(select(func.coalesce(func.sum(Order.provider_cost_snapshot), 0)).where(Order.status == OrderStatus.COMPLETED))).scalar() or Decimal("0")
        total_refunds = (await db.execute(select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(WalletTransaction.type == TransactionType.REFUND))).scalar() or Decimal("0")
        manual_credit = (await db.execute(select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(WalletTransaction.type == TransactionType.ADMIN_ADJUSTMENT, WalletTransaction.direction == TransactionDirection.CREDIT))).scalar() or Decimal("0")
        manual_debit = (await db.execute(select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(WalletTransaction.type == TransactionType.ADMIN_ADJUSTMENT, WalletTransaction.direction == TransactionDirection.DEBIT))).scalar() or Decimal("0")

    gross_profit = total_sales - total_cost
    manual_adjustments = manual_credit - manual_debit
    net_profit = gross_profit - total_refunds + manual_adjustments

    text = (
        "💰 <b>Finance</b>\n\n"
        f"Total Deposits: ৳{total_deposits:.2f}\n"
        f"Total Sales: ৳{total_sales:.2f}\n"
        f"Total Provider Cost: ৳{total_cost:.2f}\n"
        f"Gross Profit: ৳{gross_profit:.2f}\n"
        f"Refunds: ৳{total_refunds:.2f}\n"
        f"Manual Adjustments: ৳{manual_adjustments:.2f}\n"
        f"<b>Net Profit: ৳{net_profit:.2f}</b>"
    )
    await message.answer(text, parse_mode="HTML")


# =============================================================== BROADCAST =
@router.message(F.text == "📢 Broadcast")
async def admin_broadcast_start(message: Message):
    await message.answer("📢 কাদের পাঠাবেন?", reply_markup=admin_broadcast_target_kb())


@router.callback_query(F.data == "admin_broadcast_scheduled_list")
async def admin_broadcast_scheduled_list(callback: CallbackQuery):
    async with session_scope() as db:
        rows = await broadcast_service.list_pending(db)
    await callback.message.answer("📋 <b>শিডিউল করা Broadcast</b>", parse_mode="HTML", reply_markup=admin_scheduled_broadcasts_list_kb(rows))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_broadcast_cancel:"))
async def admin_broadcast_cancel(callback: CallbackQuery):
    broadcast_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        await broadcast_service.cancel_scheduled(db, broadcast_id=UUID(broadcast_id))
        rows = await broadcast_service.list_pending(db)
    await callback.message.edit_text(
        "✅ বাতিল করা হয়েছে।\n\n📋 <b>শিডিউল করা Broadcast</b>", parse_mode="HTML",
        reply_markup=admin_scheduled_broadcasts_list_kb(rows),
    )
    await callback.answer("✅ Canceled")


@router.callback_query(F.data.startswith("admin_broadcast_target:"))
async def admin_broadcast_target(callback: CallbackQuery, state: FSMContext):
    target = callback.data.split(":", 1)[1]
    await state.update_data(broadcast_target=target)
    await state.set_state(AdminBroadcastStates.waiting_message)
    await callback.message.answer("✍️ মেসেজ লিখুন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminBroadcastStates.waiting_message, F.text)
async def admin_broadcast_message_received(message: Message, state: FSMContext):
    await state.update_data(broadcast_text=message.text)
    await message.answer("কখন পাঠাবেন?", reply_markup=admin_broadcast_schedule_choice_kb())


@router.callback_query(AdminBroadcastStates.waiting_message, F.data == "admin_broadcast_now")
async def admin_broadcast_send_now(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target, text = data["broadcast_target"], data["broadcast_text"]
    await state.clear()

    await callback.message.answer("📤 Broadcast শুরু হয়েছে ব্যাকগ্রাউন্ডে... সম্পূর্ণ হলে জানানো হবে।", reply_markup=admin_menu_kb())
    asyncio.create_task(broadcast_service.run_immediate_broadcast(
        bot=callback.bot, target=target, text=text, notify_admin_id=callback.from_user.id,
    ))
    await callback.answer()


@router.callback_query(AdminBroadcastStates.waiting_message, F.data == "admin_broadcast_schedule")
async def admin_broadcast_ask_schedule(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminBroadcastStates.waiting_schedule_minutes)
    await callback.message.answer("⏰ কত মিনিট পরে পাঠাতে চান? (যেমন: 60 মানে ১ ঘণ্টা পর):", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminBroadcastStates.waiting_schedule_minutes, F.text)
async def admin_broadcast_schedule_save(message: Message, state: FSMContext):
    v = message.text.strip()
    if not v.isdigit() or int(v) <= 0:
        await message.answer("❌ ০ এর বেশি একটি সংখ্যা (মিনিট) দিন।")
        return

    data = await state.get_data()
    await state.clear()
    target, text = data["broadcast_target"], data["broadcast_text"]
    scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=int(v))

    async with session_scope() as db:
        await broadcast_service.create_scheduled(
            db, target=target, message=text, scheduled_at=scheduled_at, admin_telegram_id=message.from_user.id,
        )
    await message.answer(
        f"✅ Broadcast শিডিউল করা হয়েছে। {v} মিনিট পরে ({scheduled_at.strftime('%d %b %H:%M UTC')}) পাঠানো হবে।",
        reply_markup=admin_menu_kb(),
    )


# ================================================================ SETTINGS =
@router.message(F.text == "⚙️ Settings")
async def admin_settings_menu(message: Message):
    async with session_scope() as db:
        general = await get_setting(db, "general")
        referral = await get_setting(db, "referral")
        loyalty = await get_setting(db, "loyalty")

    text = (
        "⚙️ <b>Settings</b>\n\n"
        f"🤖 Bot Username: @{general.get('bot_username') or '-'}\n"
        f"📞 Support Username: @{general.get('support_username') or '-'}\n"
        f"🚧 Maintenance Mode: {'✅ On' if general.get('maintenance_mode') else '❌ Off'}\n\n"
        f"🎁 Referral: {'✅ On' if referral.get('enabled') else '❌ Off'}\n"
        f"🎁 Bonus: ৳{referral.get('bonus_amount', '0')}\n"
        f"🎁 Min Deposit: ৳{referral.get('min_deposit', '0')}\n\n"
        f"🎯 Cashback: {loyalty.get('cashback_percent', '0')}%\n"
        f"💱 Redeem Rate: {loyalty.get('redeem_rate', '10')} points = ৳1"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=admin_settings_menu_kb())


@router.callback_query(F.data == "admin_settings_referral_toggle")
async def admin_settings_referral_toggle(callback: CallbackQuery):
    async with session_scope() as db:
        referral = await get_setting(db, "referral")
        referral["enabled"] = not referral.get("enabled", False)
        await upsert_setting(db, "referral", referral)
    await callback.answer(f"রেফারেল এখন {'চালু' if referral['enabled'] else 'বন্ধ'}", show_alert=True)


@router.callback_query(F.data == "admin_settings_maintenance_toggle")
async def admin_settings_maintenance_toggle(callback: CallbackQuery):
    async with session_scope() as db:
        general = await get_setting(db, "general")
        general["maintenance_mode"] = not general.get("maintenance_mode", False)
        await upsert_setting(db, "general", general)
    await callback.answer(f"Maintenance Mode এখন {'চালু' if general['maintenance_mode'] else 'বন্ধ'}", show_alert=True)


@router.callback_query(F.data == "admin_settings_referral_bonus")
async def admin_settings_referral_bonus_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettingsStates.waiting_referral_bonus)
    await callback.message.answer("🎁 নতুন Referral Bonus (৳) লিখুন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminSettingsStates.waiting_referral_bonus, F.text)
async def admin_settings_referral_bonus_save(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("❌ সঠিক সংখ্যা লিখুন।")
        return
    await state.clear()
    async with session_scope() as db:
        referral = await get_setting(db, "referral")
        referral["bonus_amount"] = str(value)
        await upsert_setting(db, "referral", referral)
    await message.answer("✅ আপডেট হয়েছে।", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_settings_referral_min")
async def admin_settings_referral_min_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettingsStates.waiting_referral_min_deposit)
    await callback.message.answer("🎁 Minimum Deposit Requirement (৳) লিখুন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminSettingsStates.waiting_referral_min_deposit, F.text)
async def admin_settings_referral_min_save(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("❌ সঠিক সংখ্যা লিখুন।")
        return
    await state.clear()
    async with session_scope() as db:
        referral = await get_setting(db, "referral")
        referral["min_deposit"] = str(value)
        await upsert_setting(db, "referral", referral)
    await message.answer("✅ আপডেট হয়েছে।", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_settings_cashback_percent")
async def admin_settings_cashback_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettingsStates.waiting_cashback_percent)
    await callback.message.answer(
        "🎯 প্রতিটি সম্পন্ন অর্ডারের কত শতাংশ Loyalty Point (Cashback) হিসেবে দেওয়া হবে? (যেমন: 2 মানে 2%, বন্ধ রাখতে 0 দিন)",
        reply_markup=admin_cancel_kb(),
    )
    await callback.answer()


@router.message(AdminSettingsStates.waiting_cashback_percent, F.text)
async def admin_settings_cashback_save(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
        if value < 0 or value > 100:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ ০ থেকে ১০০ এর মধ্যে একটি সংখ্যা দিন।")
        return
    await state.clear()
    async with session_scope() as db:
        loyalty = await get_setting(db, "loyalty")
        loyalty["cashback_percent"] = str(value)
        await upsert_setting(db, "loyalty", loyalty)
    await message.answer("✅ আপডেট হয়েছে।", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_settings_redeem_rate")
async def admin_settings_redeem_rate_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettingsStates.waiting_redeem_rate)
    await callback.message.answer(
        "💱 কত পয়েন্টে ৳1 পাওয়া যাবে? (যেমন: 10 মানে 10 পয়েন্ট = ৳1)",
        reply_markup=admin_cancel_kb(),
    )
    await callback.answer()


@router.message(AdminSettingsStates.waiting_redeem_rate, F.text)
async def admin_settings_redeem_rate_save(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
        if value <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ ০ এর বেশি একটি সংখ্যা দিন।")
        return
    await state.clear()
    async with session_scope() as db:
        loyalty = await get_setting(db, "loyalty")
        loyalty["redeem_rate"] = str(value)
        await upsert_setting(db, "loyalty", loyalty)
    await message.answer("✅ আপডেট হয়েছে।", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_settings_support_username")
async def admin_settings_support_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettingsStates.waiting_support_username)
    await callback.message.answer("📞 Support Username লিখুন (@ ছাড়া):", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminSettingsStates.waiting_support_username, F.text)
async def admin_settings_support_save(message: Message, state: FSMContext):
    await state.clear()
    async with session_scope() as db:
        general = await get_setting(db, "general")
        general["support_username"] = message.text.strip().lstrip("@")
        await upsert_setting(db, "general", general)
    await message.answer("✅ আপডেট হয়েছে।", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_settings_bot_username")
async def admin_settings_bot_username_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettingsStates.waiting_bot_username)
    await callback.message.answer("🤖 Bot Username লিখুন (@ ছাড়া, রেফারেল লিংকের জন্য):", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminSettingsStates.waiting_bot_username, F.text)
async def admin_settings_bot_username_save(message: Message, state: FSMContext):
    await state.clear()
    async with session_scope() as db:
        general = await get_setting(db, "general")
        general["bot_username"] = message.text.strip().lstrip("@")
        await upsert_setting(db, "general", general)
    await message.answer("✅ আপডেট হয়েছে।", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_settings_payment_methods")
async def admin_settings_payment_methods(callback: CallbackQuery):
    async with session_scope() as db:
        methods = (await db.execute(select(PaymentMethod).order_by(PaymentMethod.sort_order.asc()))).scalars().all()
    await callback.message.answer("💳 <b>Payment Methods</b>", parse_mode="HTML", reply_markup=admin_payment_methods_kb(methods))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_pm_toggle:"))
async def admin_pm_toggle(callback: CallbackQuery):
    pm_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        method = await db.get(PaymentMethod, pm_id)
        method.is_active = not method.is_active
        methods = (await db.execute(select(PaymentMethod).order_by(PaymentMethod.sort_order.asc()))).scalars().all()
    await callback.message.edit_reply_markup(reply_markup=admin_payment_methods_kb(methods))
    await callback.answer("✅ আপডেট হয়েছে")


@router.callback_query(F.data == "admin_pm_add")
async def admin_pm_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddPaymentMethodStates.name)
    await callback.message.answer("💳 Payment Method নাম লিখুন (যেমন: bKash):", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminAddPaymentMethodStates.name, F.text)
async def admin_pm_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddPaymentMethodStates.account_number)
    await message.answer("📱 Account Number লিখুন:")


@router.message(AdminAddPaymentMethodStates.account_number, F.text)
async def admin_pm_add_number(message: Message, state: FSMContext):
    await state.update_data(account_number=message.text.strip())
    await state.set_state(AdminAddPaymentMethodStates.account_type)
    await message.answer("Account Type লিখুন (Personal/Agent/Merchant), অথবা - দিয়ে Personal রাখুন:")


@router.message(AdminAddPaymentMethodStates.account_type, F.text)
async def admin_pm_add_type(message: Message, state: FSMContext):
    v = message.text.strip()
    await state.update_data(account_type="Personal" if v == "-" else v)
    await state.set_state(AdminAddPaymentMethodStates.instructions)
    await message.answer("ইউজারদের জন্য নির্দেশনা লিখুন, অথবা - দিয়ে খালি রাখুন:")


@router.message(AdminAddPaymentMethodStates.instructions, F.text)
async def admin_pm_add_instructions(message: Message, state: FSMContext):
    v = message.text.strip()
    data = await state.get_data()
    await state.clear()

    async with session_scope() as db:
        db.add(PaymentMethod(
            name=data["name"], account_number=data["account_number"], account_type=data["account_type"],
            instructions=None if v == "-" else v, is_active=True,
        ))

    await message.answer(f"✅ Payment Method '{data['name']}' যোগ করা হয়েছে।", reply_markup=admin_menu_kb())


# ==================================================================== LOGS =
@router.message(F.text == "📝 Logs")
async def admin_logs(message: Message):
    async with session_scope() as db:
        logs = (await db.execute(select(AdminLog).order_by(desc(AdminLog.created_at)).limit(15))).scalars().all()

    if not logs:
        await message.answer("📭 কোনো লগ নেই।")
        return

    lines = ["📝 <b>সাম্প্রতিক Admin Logs</b>\n"]
    for log in logs:
        lines.append(
            f"👤 {log.admin_telegram_id} · <b>{log.action}</b>\n"
            f"{log.target_type or ''} {str(log.target_id or '')[:8]}\n"
            f"{log.created_at.strftime('%d %b, %H:%M:%S')}\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")

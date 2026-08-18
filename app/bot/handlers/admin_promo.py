"""
Admin-only management for Promo Codes and VIP Tiers. Split out from admin.py (which was
already large) but reuses the exact same AdminFilter access-control pattern -- only
Telegram accounts in settings.TELEGRAM_ADMIN_IDS ever match this router.
"""
from decimal import Decimal, InvalidOperation
from uuid import UUID

from aiogram import Router, F
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.config import get_settings
from app.database import session_scope
from app.models import PromoCode, VipTier
from app.services import promo_service, vip_service
from app.bot.states import AdminAddPromoStates, AdminAddVipTierStates
from app.bot.keyboards import (
    admin_menu_kb, admin_cancel_kb,
    admin_promos_list_kb, admin_promo_detail_kb, admin_promo_delete_confirm_kb, admin_promo_discount_type_kb,
    admin_vip_tiers_list_kb, admin_vip_tier_detail_kb, admin_vip_delete_confirm_kb,
)

settings = get_settings()
router = Router(name="admin_promo")


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.telegram_admin_id_list


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


# ============================================================= PROMO CODES =
def _promo_detail_text(promo) -> str:
    return (
        f"🏷️ <b>{promo.code}</b>\n\n"
        f"ছাড়: {promo.discount_value}{'%' if promo.discount_type == 'PERCENT' else ' ৳'}\n"
        f"ব্যবহার: {promo.used_count}/{promo.max_uses or '∞'}\n"
        f"প্রতি ইউজার সর্বোচ্চ: {promo.max_uses_per_user}\n"
        f"ন্যূনতম অর্ডার: ৳{promo.min_order_amount or '0'}\n"
        f"মেয়াদ: {promo.valid_until.strftime('%d %b %Y') if promo.valid_until else 'কোনো মেয়াদ নেই'}\n"
        f"স্ট্যাটাস: {'🟢 Active' if promo.is_active else '🔴 Inactive'}"
    )


@router.message(F.text == "🏷️ Promo Codes")
async def promo_list_menu(message: Message):
    async with session_scope() as db:
        promos = await promo_service.list_promos(db)
    await message.answer("🏷️ <b>Promo Codes</b>", parse_mode="HTML", reply_markup=admin_promos_list_kb(promos))


@router.callback_query(F.data == "pm_list")
async def promo_list_cb(callback: CallbackQuery):
    async with session_scope() as db:
        promos = await promo_service.list_promos(db)
    await callback.message.edit_text("🏷️ <b>Promo Codes</b>", parse_mode="HTML", reply_markup=admin_promos_list_kb(promos))
    await callback.answer()


@router.callback_query(F.data.startswith("pm_v:"))
async def promo_view(callback: CallbackQuery):
    promo_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        promo = await db.get(PromoCode, promo_id)
    await callback.message.edit_text(_promo_detail_text(promo), parse_mode="HTML", reply_markup=admin_promo_detail_kb(promo))
    await callback.answer()


@router.callback_query(F.data.startswith("pm_tog:"))
async def promo_toggle(callback: CallbackQuery):
    promo_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        promo = await promo_service.toggle_promo(db, promo_id=UUID(promo_id))
    await callback.message.edit_text(_promo_detail_text(promo), parse_mode="HTML", reply_markup=admin_promo_detail_kb(promo))
    await callback.answer("✅ আপডেট হয়েছে")


@router.callback_query(F.data.startswith("pm_delc:"))
async def promo_delete_confirm(callback: CallbackQuery):
    promo_id = callback.data.split(":", 1)[1]
    await callback.message.edit_text("⚠️ এই প্রোমো কোডটি মুছে ফেলতে চান?", reply_markup=admin_promo_delete_confirm_kb(promo_id))
    await callback.answer()


@router.callback_query(F.data.startswith("pm_del:"))
async def promo_delete(callback: CallbackQuery):
    promo_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        code = await promo_service.delete_promo(db, promo_id=UUID(promo_id))
        promos = await promo_service.list_promos(db)
    await callback.message.edit_text(
        f"🗑️ '{code}' মুছে ফেলা হয়েছে।\n\n🏷️ <b>Promo Codes</b>", parse_mode="HTML", reply_markup=admin_promos_list_kb(promos)
    )
    await callback.answer("✅ Deleted")


@router.callback_query(F.data == "pm_add")
async def promo_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddPromoStates.code)
    await callback.message.answer("🏷️ প্রোমো কোড লিখুন (যেমন: EID2026):", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminAddPromoStates.code, F.text)
async def promo_add_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip().upper())
    await state.set_state(AdminAddPromoStates.discount_type)
    await message.answer("ছাড়ের ধরণ বেছে নিন:", reply_markup=admin_promo_discount_type_kb())


@router.callback_query(AdminAddPromoStates.discount_type, F.data.startswith("pm_dt:"))
async def promo_add_discount_type(callback: CallbackQuery, state: FSMContext):
    discount_type = callback.data.split(":", 1)[1]
    await state.update_data(discount_type=discount_type)
    await state.set_state(AdminAddPromoStates.discount_value)
    label = "শতাংশ (যেমন: 10)" if discount_type == "PERCENT" else "টাকার পরিমাণ (যেমন: 50)"
    await callback.message.answer(f"ছাড়ের মান লিখুন — {label}:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminAddPromoStates.discount_value, F.text)
async def promo_add_discount_value(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
        if value <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ সঠিক একটি সংখ্যা দিন।")
        return
    await state.update_data(discount_value=str(value))
    await state.set_state(AdminAddPromoStates.max_uses)
    await message.answer("সর্বমোট কতবার ব্যবহার করা যাবে? (সীমাহীন রাখতে - পাঠান):")


@router.message(AdminAddPromoStates.max_uses, F.text)
async def promo_add_max_uses(message: Message, state: FSMContext):
    v = message.text.strip()
    max_uses = None if v == "-" else (int(v) if v.isdigit() else None)
    await state.update_data(max_uses=max_uses)
    await state.set_state(AdminAddPromoStates.max_uses_per_user)
    await message.answer("প্রতি ইউজার সর্বোচ্চ কতবার ব্যবহার করতে পারবে? (ডিফল্ট 1 এর জন্য -):")


@router.message(AdminAddPromoStates.max_uses_per_user, F.text)
async def promo_add_max_uses_per_user(message: Message, state: FSMContext):
    v = message.text.strip()
    max_uses_per_user = 1 if v == "-" else (int(v) if v.isdigit() else 1)
    await state.update_data(max_uses_per_user=max_uses_per_user)
    await state.set_state(AdminAddPromoStates.min_order_amount)
    await message.answer("ন্যূনতম অর্ডার মূল্য (৳)? (কোনো শর্ত না থাকলে -):")


@router.message(AdminAddPromoStates.min_order_amount, F.text)
async def promo_add_min_order(message: Message, state: FSMContext):
    v = message.text.strip()
    try:
        min_order = None if v == "-" else Decimal(v)
    except InvalidOperation:
        min_order = None
    await state.update_data(min_order_amount=str(min_order) if min_order is not None else "")
    await state.set_state(AdminAddPromoStates.valid_days)
    await message.answer("কতদিন পর্যন্ত এই কোড কার্যকর থাকবে? (কোনো মেয়াদ না রাখতে -):")


@router.message(AdminAddPromoStates.valid_days, F.text)
async def promo_add_valid_days(message: Message, state: FSMContext):
    v = message.text.strip()
    valid_days = None if v == "-" else (int(v) if v.isdigit() else None)
    data = await state.get_data()
    await state.clear()

    async with session_scope() as db:
        promo = await promo_service.create_promo(
            db, admin_telegram_id=message.from_user.id, code=data["code"],
            discount_type=data["discount_type"], discount_value=Decimal(data["discount_value"]),
            max_uses=data.get("max_uses"), max_uses_per_user=data.get("max_uses_per_user", 1),
            min_order_amount=Decimal(data["min_order_amount"]) if data.get("min_order_amount") else None,
            valid_days=valid_days,
        )
    await message.answer(f"✅ প্রোমো কোড '{promo.code}' তৈরি হয়েছে।", reply_markup=admin_menu_kb())


# =============================================================== VIP TIERS =
def _tier_detail_text(tier) -> str:
    return (
        f"👑 <b>{tier.name}</b>\n\n"
        f"ন্যূনতম খরচ: ৳{tier.min_total_spent:.0f}+\n"
        f"ছাড়: {tier.discount_percent}%\n"
        f"স্ট্যাটাস: {'🟢 Active' if tier.is_active else '🔴 Inactive'}"
    )


@router.message(F.text == "👑 VIP Tiers")
async def vip_list_menu(message: Message):
    async with session_scope() as db:
        tiers = await vip_service.list_tiers(db)
    await message.answer(
        "👑 <b>VIP Tiers</b>\n\nইউজারের মোট (COMPLETED) খরচের উপর ভিত্তি করে সর্বোচ্চ যোগ্য tier-এর ছাড় স্বয়ংক্রিয়ভাবে প্রয়োগ হবে।",
        parse_mode="HTML", reply_markup=admin_vip_tiers_list_kb(tiers),
    )


@router.callback_query(F.data == "vt_list")
async def vip_list_cb(callback: CallbackQuery):
    async with session_scope() as db:
        tiers = await vip_service.list_tiers(db)
    await callback.message.edit_text("👑 <b>VIP Tiers</b>", parse_mode="HTML", reply_markup=admin_vip_tiers_list_kb(tiers))
    await callback.answer()


@router.callback_query(F.data.startswith("vt_v:"))
async def vip_view(callback: CallbackQuery):
    tier_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        tier = await db.get(VipTier, tier_id)
    await callback.message.edit_text(_tier_detail_text(tier), parse_mode="HTML", reply_markup=admin_vip_tier_detail_kb(tier))
    await callback.answer()


@router.callback_query(F.data.startswith("vt_tog:"))
async def vip_toggle(callback: CallbackQuery):
    tier_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        tier = await vip_service.toggle_tier(db, tier_id=UUID(tier_id))
    await callback.message.edit_text(_tier_detail_text(tier), parse_mode="HTML", reply_markup=admin_vip_tier_detail_kb(tier))
    await callback.answer("✅ আপডেট হয়েছে")


@router.callback_query(F.data.startswith("vt_delc:"))
async def vip_delete_confirm(callback: CallbackQuery):
    tier_id = callback.data.split(":", 1)[1]
    await callback.message.edit_text("⚠️ এই VIP Tier-টি মুছে ফেলতে চান?", reply_markup=admin_vip_delete_confirm_kb(tier_id))
    await callback.answer()


@router.callback_query(F.data.startswith("vt_del:"))
async def vip_delete(callback: CallbackQuery):
    tier_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        name = await vip_service.delete_tier(db, tier_id=UUID(tier_id))
        tiers = await vip_service.list_tiers(db)
    await callback.message.edit_text(
        f"🗑️ '{name}' মুছে ফেলা হয়েছে।\n\n👑 <b>VIP Tiers</b>", parse_mode="HTML", reply_markup=admin_vip_tiers_list_kb(tiers)
    )
    await callback.answer("✅ Deleted")


@router.callback_query(F.data == "vt_add")
async def vip_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddVipTierStates.name)
    await callback.message.answer("👑 Tier-এর নাম লিখুন (যেমন: Silver, Gold, Platinum):", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminAddVipTierStates.name, F.text)
async def vip_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddVipTierStates.min_total_spent)
    await message.answer("ন্যূনতম মোট খরচ (৳) কত হলে এই Tier পাবে?")


@router.message(AdminAddVipTierStates.min_total_spent, F.text)
async def vip_add_min_spent(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
        if value < 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ সঠিক একটি সংখ্যা দিন।")
        return
    await state.update_data(min_total_spent=str(value))
    await state.set_state(AdminAddVipTierStates.discount_percent)
    await message.answer("এই Tier-এ কত শতাংশ ছাড় থাকবে? (যেমন: 5):")


@router.message(AdminAddVipTierStates.discount_percent, F.text)
async def vip_add_discount_percent(message: Message, state: FSMContext):
    try:
        value = Decimal(message.text.strip())
        if value <= 0 or value > 100:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("❌ ০ থেকে ১০০ এর মধ্যে একটি সংখ্যা দিন।")
        return
    data = await state.get_data()
    await state.clear()

    async with session_scope() as db:
        tier = await vip_service.create_tier(
            db, name=data["name"], min_total_spent=Decimal(data["min_total_spent"]), discount_percent=value,
        )
    await message.answer(f"✅ VIP Tier '{tier.name}' তৈরি হয়েছে।", reply_markup=admin_menu_kb())

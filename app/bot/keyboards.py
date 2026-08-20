from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="💎 ডায়মন্ড কিনুন"), KeyboardButton(text="🔎 চেক UID")],
        [KeyboardButton(text="🎁 বাল্ক অর্ডার"), KeyboardButton(text="💰 আমার ব্যালেন্স")],
        [KeyboardButton(text="➕ টাকা জমা দিন"), KeyboardButton(text="📦 আমার অর্ডার")],
        [KeyboardButton(text="💳 লেনদেন"), KeyboardButton(text="🎁 রেফার & আয়")],
        [KeyboardButton(text="🎯 লয়্যালটি পয়েন্ট"), KeyboardButton(text="👤 আমার প্রোফাইল")],
        [KeyboardButton(text="📞 সাপোর্ট")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 ফিরে যান")]], resize_keyboard=True)


def uid_valid_kb(uid: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="💎 এই UID-তে Diamond কিনুন", callback_data=f"buy_for_uid:{uid}")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def packages_kb(packages: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"💎 {p.diamond_amount} Diamonds — ৳{p.selling_price:.0f}",
            callback_data=f"select_package:{p.id}",
        )]
        for p in packages
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def bulk_packages_kb(packages: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"💎 {p.diamond_amount} Diamonds — ৳{p.selling_price:.0f}",
            callback_data=f"bulk_select_package:{p.id}",
        )]
        for p in packages
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_purchase_kb(promo_applied: bool = False) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="✅ Confirm Purchase", callback_data="confirm_purchase"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_purchase"),
    ]]
    promo_text = "🏷️ প্রোমো কোড পরিবর্তন করুন" if promo_applied else "🏷️ প্রোমো কোড আছে?"
    rows.append([InlineKeyboardButton(text=promo_text, callback_data="enter_promo_code")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def insufficient_balance_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ টাকা জমা দিন", callback_data="go_deposit")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="go_menu")],
    ])


def payment_methods_kb(methods: list) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"💳 {m.name}", callback_data=f"select_payment_method:{m.id}")] for m in methods]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def support_kb(support_username: str) -> InlineKeyboardMarkup:
    username = support_username.lstrip("@")
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📞 Support", url=f"https://t.me/{username}")
    ]])


def loyalty_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💱 পয়েন্ট রিডিম করুন", callback_data="redeem_points"),
    ]])


# ============================================================ ADMIN MENU ===
def admin_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📊 Dashboard"), KeyboardButton(text="🔌 Providers")],
        [KeyboardButton(text="📦 Packages"), KeyboardButton(text="🛒 Orders")],
        [KeyboardButton(text="💳 Deposits"), KeyboardButton(text="👥 Users")],
        [KeyboardButton(text="🏷️ Promo Codes"), KeyboardButton(text="👑 VIP Tiers")],
        [KeyboardButton(text="🎫 Support Tickets"), KeyboardButton(text="⭐ Reviews")],
        [KeyboardButton(text="🚩 Flagged Users"), KeyboardButton(text="💰 Finance")],
        [KeyboardButton(text="📢 Broadcast"), KeyboardButton(text="⚙️ Settings")],
        [KeyboardButton(text="📝 Logs")],
        [KeyboardButton(text="🔙 User মেনুতে ফিরুন")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ বাতিল")]], resize_keyboard=True)


def skip_inline_kb(callback_data: str = "admin_skip") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭️ Skip (Default)", callback_data=callback_data)]])


def admin_providers_list_kb(providers: list) -> InlineKeyboardMarkup:
    rows = []
    for p in providers:
        status = "🟢" if p.is_active else "🔴"
        rows.append([
            InlineKeyboardButton(text=f"{status} {p.name}", callback_data=f"admin_provider_view:{p.id}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Add Provider", callback_data="admin_provider_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_provider_detail_kb(provider) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Deactivate" if provider.is_active else "🟢 Activate"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Test Connection", callback_data=f"admin_provider_test:{provider.id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin_provider_toggle:{provider.id}")],
        [InlineKeyboardButton(text="✏️ Edit", callback_data=f"ap_edit:{provider.id}")],
        [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"ap_delc:{provider.id}")],
        [InlineKeyboardButton(text="🔙 Providers List", callback_data="admin_provider_list")],
    ])


def admin_provider_delete_confirm_kb(provider_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❗ হ্যাঁ, Delete করো", callback_data=f"ap_del:{provider_id}")],
        [InlineKeyboardButton(text="🔙 বাতিল", callback_data=f"admin_provider_view:{provider_id}")],
    ])


_EDIT_FIELD_CODES = {
    "nm": "name", "url": "base_url", "key": "api_key",
    "val": "validation_endpoint", "ord": "order_endpoint",
    "sts": "status_endpoint", "bal": "balance_endpoint", "pri": "priority",
}
EDIT_FIELD_LABELS = {v: k for k, v in {
    "nm": "Name", "url": "Base URL", "key": "API Key",
    "val": "Validation Endpoint", "ord": "Order Endpoint",
    "sts": "Status Endpoint", "bal": "Balance Endpoint", "pri": "Priority",
}.items()}


def admin_provider_edit_field_kb(provider_id) -> InlineKeyboardMarkup:
    fields = [
        ("Name", "nm"), ("Base URL", "url"), ("API Key", "key"),
        ("Validation Endpoint", "val"), ("Order Endpoint", "ord"),
        ("Status Endpoint", "sts"), ("Balance Endpoint", "bal"),
        ("Priority", "pri"),
    ]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"ap_ef:{provider_id}:{key}")]
            for label, key in fields]
    rows.append([InlineKeyboardButton(text="🔙 ফিরে যাও", callback_data=f"admin_provider_view:{provider_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_provider_code_kb(codes: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=code, callback_data=f"admin_provider_code:{code}")] for code in codes
    ])


def admin_packages_list_kb(packages: list) -> InlineKeyboardMarkup:
    rows = []
    for p in packages:
        status = "🟢" if p.is_active else "🔴"
        rows.append([InlineKeyboardButton(
            text=f"{status} {p.diamond_amount}💎 — ৳{p.selling_price:.0f}",
            callback_data=f"admin_package_view:{p.id}",
        )])
    rows.append([InlineKeyboardButton(text="➕ Add Package", callback_data="admin_package_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_package_detail_kb(package) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Deactivate" if package.is_active else "🟢 Activate"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin_package_toggle:{package.id}")],
        [InlineKeyboardButton(text="🔙 Packages List", callback_data="admin_package_list")],
    ])


def admin_package_provider_select_kb(providers: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p.name, callback_data=f"admin_package_provider:{p.id}")] for p in providers
    ])


def admin_orders_status_filter_kb() -> InlineKeyboardMarkup:
    statuses = ["PENDING", "PROCESSING", "COMPLETED", "FAILED", "CANCELED"]
    rows = [[InlineKeyboardButton(text=s, callback_data=f"admin_orders_filter:{s}")] for s in statuses]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_actions_kb(order) -> InlineKeyboardMarkup:
    rows = []
    if order.status.value == "FAILED":
        rows.append([InlineKeyboardButton(text="🔄 Retry Order", callback_data=f"admin_order_retry:{order.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def admin_deposit_actions_kb(deposit_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"admin_deposit_approve:{deposit_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"admin_deposit_reject:{deposit_id}"),
    ]])


def admin_user_actions_kb(user) -> InlineKeyboardMarkup:
    ban_text = "✅ Unban" if user.is_banned else "🚫 Ban"
    rows = [
        [InlineKeyboardButton(text="➕/➖ Adjust Balance", callback_data=f"admin_user_adjust:{user.id}")],
        [InlineKeyboardButton(text=ban_text, callback_data=f"admin_user_ban_toggle:{user.id}")],
    ]
    if user.is_flagged:
        rows.append([InlineKeyboardButton(text="🚩 Unflag", callback_data=f"admin_user_unflag:{user.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_balance_direction_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Add", callback_data="admin_balance_dir:credit"),
        InlineKeyboardButton(text="➖ Deduct", callback_data="admin_balance_dir:debit"),
    ]])


def admin_broadcast_target_kb() -> InlineKeyboardMarkup:
    targets = [("all", "All Users"), ("active", "Active Users"), ("depositors", "Depositors"), ("buyers", "Diamond Buyers")]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"admin_broadcast_target:{key}")] for key, label in targets
    ] + [[InlineKeyboardButton(text="📋 শিডিউল করা Broadcast দেখুন", callback_data="admin_broadcast_scheduled_list")]])


def admin_broadcast_schedule_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 এখনই পাঠান", callback_data="admin_broadcast_now"),
        InlineKeyboardButton(text="⏰ শিডিউল করুন", callback_data="admin_broadcast_schedule"),
    ]])


def admin_scheduled_broadcasts_list_kb(rows: list) -> InlineKeyboardMarkup:
    kb_rows = []
    for r in rows:
        label = f"⏰ {r.scheduled_at.strftime('%d %b %H:%M')} — {r.target} ({r.message[:20]}…)"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"admin_broadcast_cancel:{r.id}")])
    if not kb_rows:
        kb_rows = [[InlineKeyboardButton(text="(কোনো শিডিউল করা Broadcast নেই)", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


def admin_settings_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Referral Toggle", callback_data="admin_settings_referral_toggle")],
        [InlineKeyboardButton(text="🎁 Set Referral Bonus", callback_data="admin_settings_referral_bonus")],
        [InlineKeyboardButton(text="🎁 Set Min Deposit", callback_data="admin_settings_referral_min")],
        [InlineKeyboardButton(text="📞 Set Support Username", callback_data="admin_settings_support_username")],
        [InlineKeyboardButton(text="🤖 Set Bot Username", callback_data="admin_settings_bot_username")],
        [InlineKeyboardButton(text="🚧 Maintenance Mode Toggle", callback_data="admin_settings_maintenance_toggle")],
        [InlineKeyboardButton(text="💳 Payment Methods", callback_data="admin_settings_payment_methods")],
        [InlineKeyboardButton(text="🎯 Set Cashback %", callback_data="admin_settings_cashback_percent")],
        [InlineKeyboardButton(text="💱 Set Points Redeem Rate", callback_data="admin_settings_redeem_rate")],
    ])


def admin_payment_methods_kb(methods: list) -> InlineKeyboardMarkup:
    rows = []
    for m in methods:
        status = "🟢" if m.is_active else "🔴"
        rows.append([InlineKeyboardButton(text=f"{status} {m.name} ({m.account_number})", callback_data=f"admin_pm_toggle:{m.id}")])
    rows.append([InlineKeyboardButton(text="➕ Add Payment Method", callback_data="admin_pm_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==================================================== ADMIN: PROMO CODES ===
def admin_promos_list_kb(promos: list) -> InlineKeyboardMarkup:
    rows = []
    for p in promos:
        status = "🟢" if p.is_active else "🔴"
        rows.append([InlineKeyboardButton(text=f"{status} {p.code} ({p.used_count}/{p.max_uses or '∞'})", callback_data=f"pm_v:{p.id}")])
    rows.append([InlineKeyboardButton(text="➕ Add Promo Code", callback_data="pm_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_promo_detail_kb(promo) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Deactivate" if promo.is_active else "🟢 Activate"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"pm_tog:{promo.id}")],
        [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"pm_delc:{promo.id}")],
        [InlineKeyboardButton(text="🔙 Promo List", callback_data="pm_list")],
    ])


def admin_promo_delete_confirm_kb(promo_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❗ হ্যাঁ, Delete করো", callback_data=f"pm_del:{promo_id}")],
        [InlineKeyboardButton(text="🔙 বাতিল", callback_data=f"pm_v:{promo_id}")],
    ])


def admin_promo_discount_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="% Percent", callback_data="pm_dt:PERCENT"),
        InlineKeyboardButton(text="৳ Fixed", callback_data="pm_dt:FIXED"),
    ]])


# ======================================================== ADMIN: VIP TIER ==
def admin_vip_tiers_list_kb(tiers: list) -> InlineKeyboardMarkup:
    rows = []
    for t in tiers:
        status = "🟢" if t.is_active else "🔴"
        rows.append([InlineKeyboardButton(text=f"{status} {t.name} (৳{t.min_total_spent:.0f}+, {t.discount_percent:.0f}%)", callback_data=f"vt_v:{t.id}")])
    rows.append([InlineKeyboardButton(text="➕ Add VIP Tier", callback_data="vt_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_vip_tier_detail_kb(tier) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Deactivate" if tier.is_active else "🟢 Activate"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"vt_tog:{tier.id}")],
        [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"vt_delc:{tier.id}")],
        [InlineKeyboardButton(text="🔙 VIP Tiers List", callback_data="vt_list")],
    ])


def admin_vip_delete_confirm_kb(tier_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❗ হ্যাঁ, Delete করো", callback_data=f"vt_del:{tier_id}")],
        [InlineKeyboardButton(text="🔙 বাতিল", callback_data=f"vt_v:{tier_id}")],
    ])


# ======================================================= ORDER CANCEL/RATE =
def order_cancel_kb(order_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ অর্ডার বাতিল করুন", callback_data=f"cancel_order:{order_id}")
    ]])


def rating_kb(order_id) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text="⭐" * n, callback_data=f"rate_order:{order_id}:{n}") for n in range(1, 6)]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def review_comment_kb(order_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💬 মন্তব্য যোগ করুন (ঐচ্ছিক)", callback_data=f"review_comment:{order_id}")
    ]])


# ============================================================== SUPPORT ====
def support_menu_kb(support_username: str) -> InlineKeyboardMarkup:
    username = support_username.lstrip("@")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 নতুন টিকেট খুলুন", callback_data="support_new_ticket")],
        [InlineKeyboardButton(text="📋 আমার টিকেট", callback_data="support_my_tickets")],
        [InlineKeyboardButton(text="📞 সরাসরি যোগাযোগ", url=f"https://t.me/{username}")],
    ])


def support_tickets_list_kb(tickets) -> InlineKeyboardMarkup:
    rows = []
    for t in tickets:
        status = "🟢" if t.status == "OPEN" else "⚪"
        rows.append([InlineKeyboardButton(text=f"{status} {t.subject}", callback_data=f"support_ticket_view:{t.id}")])
    if not rows:
        rows = [[InlineKeyboardButton(text="(কোনো টিকেট নেই)", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_ticket_detail_kb(ticket) -> InlineKeyboardMarkup:
    rows = []
    if ticket.status == "OPEN":
        rows.append([InlineKeyboardButton(text="✍️ উত্তর দিন", callback_data=f"support_reply:{ticket.id}")])
    rows.append([InlineKeyboardButton(text="🔙 আমার টিকেট", callback_data="support_my_tickets")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ======================================================= ADMIN: SUPPORT ====
def admin_support_tickets_list_kb(tickets) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🎫 {t.subject}", callback_data=f"adm_tkt_v:{t.id}")] for t in tickets]
    if not rows:
        rows = [[InlineKeyboardButton(text="(কোনো ওপেন টিকেট নেই)", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_ticket_detail_kb(ticket) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="✍️ Reply", callback_data=f"adm_tkt_reply:{ticket.id}")]]
    if ticket.status == "OPEN":
        rows.append([InlineKeyboardButton(text="✅ Close Ticket", callback_data=f"adm_tkt_close:{ticket.id}")])
    rows.append([InlineKeyboardButton(text="🔙 Ticket List", callback_data="adm_tkt_list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================ BULK PURCHASE
def bulk_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Confirm Bulk Purchase", callback_data="bulk_confirm"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="bulk_cancel"),
    ]])


# ============================================================ ADMIN: PHASE5
def dashboard_extra_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 বিস্তারিত চার্ট দেখুন", callback_data="admin_dashboard_chart")],
        [InlineKeyboardButton(text="📤 Export (CSV)", callback_data="admin_dashboard_export")],
    ])


def admin_export_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Orders (30 দিন)", callback_data="admin_export:orders:30")],
        [InlineKeyboardButton(text="📦 Orders (সব)", callback_data="admin_export:orders:all")],
        [InlineKeyboardButton(text="💳 Deposits (30 দিন)", callback_data="admin_export:deposits:30")],
        [InlineKeyboardButton(text="💳 Deposits (সব)", callback_data="admin_export:deposits:all")],
    ])

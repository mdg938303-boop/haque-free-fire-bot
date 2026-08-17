from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="💎 ডায়মন্ড কিনুন"), KeyboardButton(text="🔎 চেক UID")],
        [KeyboardButton(text="💰 আমার ব্যালেন্স"), KeyboardButton(text="➕ টাকা জমা দিন")],
        [KeyboardButton(text="📦 আমার অর্ডার"), KeyboardButton(text="💳 লেনদেন")],
        [KeyboardButton(text="🎁 রেফার & আয়"), KeyboardButton(text="👤 আমার প্রোফাইল")],
        [KeyboardButton(text="📞 সাপোর্ট")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 ফিরে যান")]], resize_keyboard=True)


def uid_valid_kb(package_id: str | None = None) -> InlineKeyboardMarkup:
    if package_id:
        buttons = [[InlineKeyboardButton(text="💎 এই UID-তে Diamond কিনুন", callback_data=f"buy_for_uid:{package_id}")]]
    else:
        buttons = [[InlineKeyboardButton(text="💎 এই UID-তে Diamond কিনুন", callback_data="buy_for_uid:choose")]]
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


def confirm_purchase_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Confirm Purchase", callback_data="confirm_purchase"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_purchase"),
    ]])


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


# ============================================================ ADMIN MENU ===
def admin_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📊 Dashboard"), KeyboardButton(text="🔌 Providers")],
        [KeyboardButton(text="📦 Packages"), KeyboardButton(text="🛒 Orders")],
        [KeyboardButton(text="💳 Deposits"), KeyboardButton(text="👥 Users")],
        [KeyboardButton(text="💰 Finance"), KeyboardButton(text="📢 Broadcast")],
        [KeyboardButton(text="⚙️ Settings"), KeyboardButton(text="📝 Logs")],
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
        [InlineKeyboardButton(text="🔙 Providers List", callback_data="admin_provider_list")],
    ])


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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕/➖ Adjust Balance", callback_data=f"admin_user_adjust:{user.id}")],
        [InlineKeyboardButton(text=ban_text, callback_data=f"admin_user_ban_toggle:{user.id}")],
    ])


def admin_balance_direction_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Add", callback_data="admin_balance_dir:credit"),
        InlineKeyboardButton(text="➖ Deduct", callback_data="admin_balance_dir:debit"),
    ]])


def admin_broadcast_target_kb() -> InlineKeyboardMarkup:
    targets = [("all", "All Users"), ("active", "Active Users"), ("depositors", "Depositors"), ("buyers", "Diamond Buyers")]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"admin_broadcast_target:{key}")] for key, label in targets
    ])


def admin_settings_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Referral Toggle", callback_data="admin_settings_referral_toggle")],
        [InlineKeyboardButton(text="🎁 Set Referral Bonus", callback_data="admin_settings_referral_bonus")],
        [InlineKeyboardButton(text="🎁 Set Min Deposit", callback_data="admin_settings_referral_min")],
        [InlineKeyboardButton(text="📞 Set Support Username", callback_data="admin_settings_support_username")],
        [InlineKeyboardButton(text="🤖 Set Bot Username", callback_data="admin_settings_bot_username")],
        [InlineKeyboardButton(text="🚧 Maintenance Mode Toggle", callback_data="admin_settings_maintenance_toggle")],
        [InlineKeyboardButton(text="💳 Payment Methods", callback_data="admin_settings_payment_methods")],
    ])


def admin_payment_methods_kb(methods: list) -> InlineKeyboardMarkup:
    rows = []
    for m in methods:
        status = "🟢" if m.is_active else "🔴"
        rows.append([InlineKeyboardButton(text=f"{status} {m.name} ({m.account_number})", callback_data=f"admin_pm_toggle:{m.id}")])
    rows.append([InlineKeyboardButton(text="➕ Add Payment Method", callback_data="admin_pm_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

from aiogram.fsm.state import State, StatesGroup


class UidCheckStates(StatesGroup):
    waiting_uid = State()


class PurchaseStates(StatesGroup):
    waiting_uid = State()
    confirming = State()
    waiting_promo_code = State()


class LoyaltyStates(StatesGroup):
    waiting_redeem_points = State()


class SupportStates(StatesGroup):
    waiting_new_ticket_message = State()
    waiting_ticket_reply = State()


class ReviewStates(StatesGroup):
    waiting_comment = State()


class OnboardingStates(StatesGroup):
    waiting_reseller_username = State()
    waiting_reseller_password = State()


class ResellerApplyStates(StatesGroup):
    waiting_message = State()


class AdminResellerStates(StatesGroup):
    waiting_username = State()
    waiting_password = State()
    waiting_flat_percent = State()
    waiting_custom_price = State()
    waiting_reset_password = State()
    waiting_reject_reason = State()


class AdminSupportStates(StatesGroup):
    waiting_reply = State()


class DepositStates(StatesGroup):
    waiting_amount = State()
    waiting_reference = State()


# --------------------------------------------------------- admin states ---
class AdminAddProviderStates(StatesGroup):
    name = State()
    code = State()
    base_url = State()
    api_key = State()
    validation_endpoint = State()
    order_endpoint = State()
    status_endpoint = State()
    balance_endpoint = State()
    priority = State()


class AdminEditProviderStates(StatesGroup):
    value = State()


class AdminAddPackageStates(StatesGroup):
    name = State()
    diamond_amount = State()
    selling_price = State()
    provider_select = State()
    provider_product_id = State()
    provider_cost = State()


class AdminAdjustBalanceStates(StatesGroup):
    waiting_user_lookup = State()
    waiting_amount = State()
    waiting_reason = State()


class AdminBroadcastStates(StatesGroup):
    waiting_message = State()
    waiting_schedule_minutes = State()


class AdminAddPaymentMethodStates(StatesGroup):
    name = State()
    account_number = State()
    account_type = State()
    instructions = State()


class AdminSettingsStates(StatesGroup):
    waiting_referral_bonus = State()
    waiting_referral_min_deposit = State()
    waiting_support_username = State()
    waiting_bot_username = State()
    waiting_cashback_percent = State()
    waiting_redeem_rate = State()


class AdminAddPromoStates(StatesGroup):
    code = State()
    discount_type = State()
    discount_value = State()
    max_uses = State()
    max_uses_per_user = State()
    min_order_amount = State()
    valid_days = State()


class AdminAddVipTierStates(StatesGroup):
    name = State()
    min_total_spent = State()
    discount_percent = State()


class BulkPurchaseStates(StatesGroup):
    waiting_uids = State()
    confirming = State()

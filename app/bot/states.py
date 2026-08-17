from aiogram.fsm.state import State, StatesGroup


class UidCheckStates(StatesGroup):
    waiting_uid = State()


class PurchaseStates(StatesGroup):
    waiting_uid = State()
    confirming = State()


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

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric,
    String, Text, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# ---------------------------------------------------------------- enums ----
class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class DepositStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    PURCHASE = "PURCHASE"
    REFERRAL_BONUS = "REFERRAL_BONUS"
    REFUND = "REFUND"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"
    CASHBACK = "CASHBACK"


class TransactionDirection(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


# ---------------------------------------------------------------- users ----
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flag_reason: Mapped[str | None] = mapped_column(String(255))
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    referred_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    wallet: Mapped["Wallet"] = relationship(back_populates="user", uselist=False)
    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    deposits: Mapped[list["Deposit"]] = relationship(back_populates="user")


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_deposit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_purchase: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_referral_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_refund: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_cashback: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # optimistic locking
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="wallet")


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[uuid.UUID] = uuid_pk()
    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False, index=True)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, name="transaction_type"), nullable=False)
    direction: Mapped[TransactionDirection] = mapped_column(Enum(TransactionDirection, name="transaction_direction"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50))  # order/deposit/referral/admin
    reference_id: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    # Telegram numeric ID of the admin who performed this action (if any). There is no
    # separate admin_users table anymore -- admins are identified purely by Telegram ID
    # via settings.TELEGRAM_ADMIN_IDS, so this is just a plain BigInteger, not a FK.
    created_by_admin_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ------------------------------------------------------------ providers ----
class ApiProvider(Base):
    __tablename__ = "api_providers"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # e.g. "epinby" -> maps to adapter class
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(String(50), default="bearer")  # bearer / header / query / hmac
    auth_header_name: Mapped[str | None] = mapped_column(String(100))
    validation_endpoint: Mapped[str | None] = mapped_column(String(500))
    order_endpoint: Mapped[str | None] = mapped_column(String(500))
    status_endpoint: Mapped[str | None] = mapped_column(String(500))
    balance_endpoint: Mapped[str | None] = mapped_column(String(500))
    webhook_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    extra_config: Mapped[dict | None] = mapped_column(JSONB, default=dict)  # adapter-specific field mapping
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower = higher priority
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    products: Mapped[list["ProviderProduct"]] = relationship(back_populates="provider")


class ProviderProduct(Base):
    """Maps a Package to a specific provider's product id (many providers can back one package)."""
    __tablename__ = "provider_products"

    id: Mapped[uuid.UUID] = uuid_pk()
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("api_providers.id"), nullable=False)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("packages.id"), nullable=False)
    provider_product_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    provider: Mapped["ApiProvider"] = relationship(back_populates="products")
    package: Mapped["Package"] = relationship(back_populates="provider_products")

    __table_args__ = (UniqueConstraint("provider_id", "package_id", name="uq_provider_package"),)


# -------------------------------------------------------------- packages ---
class Package(Base):
    __tablename__ = "packages"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    diamond_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    game: Mapped[str] = mapped_column(String(50), default="FREEFIRE")
    region: Mapped[str] = mapped_column(String(20), default="BD")
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    primary_provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("api_providers.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    provider_products: Mapped[list["ProviderProduct"]] = relationship(back_populates="package")


# ---------------------------------------------------------------- orders ---
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("packages.id"), nullable=False)
    game_uid: Mapped[str] = mapped_column(String(50), nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(200))
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("api_providers.id"))
    provider_product_id: Mapped[str | None] = mapped_column(String(200))
    provider_cost_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    provider_order_id: Mapped[str | None] = mapped_column(String(200), index=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status"), default=OrderStatus.PENDING, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    wallet_deducted: Mapped[bool] = mapped_column(Boolean, default=False)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    promo_code: Mapped[str | None] = mapped_column(String(32))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    vip_discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    loyalty_points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loyalty_awarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_prompted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="orders")

    __table_args__ = (Index("ix_orders_status_created", "status", "created_at"),)


class OrderLog(Base):
    """Append-only trace of everything that happened to an order (provider requests/responses, retries)."""
    __tablename__ = "order_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# -------------------------------------------------------------- deposits ---
class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # bKash / Nagad / Rocket
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), default="Personal")
    instructions: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Deposit(Base):
    __tablename__ = "deposits"

    id: Mapped[uuid.UUID] = uuid_pk()
    deposit_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    payment_method_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_methods.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sender_number: Mapped[str | None] = mapped_column(String(50))
    transaction_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[DepositStatus] = mapped_column(Enum(DepositStatus, name="deposit_status"), default=DepositStatus.PENDING, nullable=False)
    admin_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_admin_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="deposits")

    __table_args__ = (UniqueConstraint("payment_method_id", "transaction_reference", name="uq_deposit_txn_ref"),)


# -------------------------------------------------------------- referrals --
class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = uuid_pk()
    referrer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    referred_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    bonus_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    bonus_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- webhook --
class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("api_providers.id"))
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)  # provider-supplied unique id for dedup
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("provider_id", "event_id", name="uq_webhook_event_dedup"),)


# ------------------------------------------------------------ idempotency --
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "order_create"
    resource_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------- admin -----
# There is no admin_users table: an "admin" is simply any Telegram account whose numeric
# ID appears in settings.TELEGRAM_ADMIN_IDS. All admin actions are still fully audited in
# AdminLog below, keyed by that Telegram ID.
class AdminLog(Base):
    __tablename__ = "admin_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    admin_telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ------------------------------------------------------------- promo codes -
class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "PERCENT" | "FIXED"
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer)  # total uses allowed across all users, null = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_uses_per_user: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_order_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_admin_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromoCodeUsage(Base):
    """One row per redemption -- used to enforce max_uses_per_user and for reporting."""
    __tablename__ = "promo_code_usages"

    id: Mapped[uuid.UUID] = uuid_pk()
    promo_code_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- VIP tiers
class VipTier(Base):
    """A user qualifies for a tier once their lifetime completed-order spend reaches
    min_total_spent. The HIGHEST qualifying tier's discount_percent is applied automatically
    at checkout -- no admin action needed per user."""
    __tablename__ = "vip_tiers"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    min_total_spent: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ------------------------------------------------------------ support desk -
class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)  # OPEN | CLOSED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("support_tickets.id"), nullable=False, index=True)
    sender_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "user" | "admin"
    sender_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ------------------------------------------------------------ order review -
class OrderReview(Base):
    __tablename__ = "order_reviews"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ------------------------------------------------------- scheduled broadcast
class ScheduledBroadcast(Base):
    __tablename__ = "scheduled_broadcasts"

    id: Mapped[uuid.UUID] = uuid_pk()
    target: Mapped[str] = mapped_column(String(20), nullable=False)  # "all" | "depositors" | "buyers"
    message: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)  # PENDING | SENT | CANCELED
    created_by_admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# ---------------------------------------------------------- reseller system
class ResellerAccount(Base):
    """Created ONLY by an admin (directly, or after approving a ResellerApplication).
    Not bound to a Telegram account until the holder logs in with the right
    username+password for the first time -- see reseller_service.authenticate().
    session_active flips back to False every time the bound user runs /start, so they
    must re-enter their password each session (per spec) before reseller pricing applies."""
    __tablename__ = "reseller_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    pricing_method: Mapped[str] = mapped_column(String(20), default="FLAT_PERCENT", nullable=False)  # FLAT_PERCENT | CUSTOM
    flat_discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)  # ACTIVE | REVOKED
    session_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResellerPackagePrice(Base):
    __tablename__ = "reseller_package_prices"
    __table_args__ = (UniqueConstraint("reseller_account_id", "package_id", name="uq_reseller_package_price"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    reseller_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reseller_accounts.id"), nullable=False, index=True)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("packages.id"), nullable=False)
    custom_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class ResellerApplication(Base):
    __tablename__ = "reseller_applications"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)  # PENDING | APPROVED | REJECTED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_admin_telegram_id: Mapped[int | None] = mapped_column(BigInteger)

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
    referred_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
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

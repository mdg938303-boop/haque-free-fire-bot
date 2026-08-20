from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResellerAccount, ResellerPackagePrice, Package
from app.core.security import hash_password, verify_password
from app.core.exceptions import (
    ResellerAuthError, ResellerAlreadyBoundError, ResellerRevokedError,
    ResellerUsernameTakenError, ResellerPriceNotSetError,
)


# ==================================================================== ADMIN
async def create_account(
    db: AsyncSession, *, admin_telegram_id: int, username: str, password: str,
    pricing_method: str, flat_discount_percent: Decimal | None = None, telegram_id: int | None = None,
) -> ResellerAccount:
    username = username.strip()
    existing = (await db.execute(select(ResellerAccount).where(ResellerAccount.username == username))).scalar_one_or_none()
    if existing is not None:
        raise ResellerUsernameTakenError(internal_detail=f"username {username!r} already exists")

    account = ResellerAccount(
        username=username, password_hash=hash_password(password), telegram_id=telegram_id,
        pricing_method=pricing_method, flat_discount_percent=flat_discount_percent,
        status="ACTIVE", created_by_admin_telegram_id=admin_telegram_id,
        bound_at=datetime.now(timezone.utc) if telegram_id else None,
    )
    db.add(account)
    await db.flush()
    return account


async def reset_password(db: AsyncSession, *, reseller_id: UUID, new_password: str) -> ResellerAccount:
    account = await db.get(ResellerAccount, reseller_id)
    account.password_hash = hash_password(new_password)
    await db.flush()
    return account


async def set_pricing_method(db: AsyncSession, *, reseller_id: UUID, pricing_method: str, flat_discount_percent: Decimal | None = None) -> ResellerAccount:
    account = await db.get(ResellerAccount, reseller_id)
    account.pricing_method = pricing_method
    if pricing_method == "FLAT_PERCENT":
        account.flat_discount_percent = flat_discount_percent
    await db.flush()
    return account


async def set_custom_price(db: AsyncSession, *, reseller_id: UUID, package_id: UUID, price: Decimal) -> ResellerPackagePrice:
    existing = (await db.execute(
        select(ResellerPackagePrice).where(
            ResellerPackagePrice.reseller_account_id == reseller_id, ResellerPackagePrice.package_id == package_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        existing.custom_price = price
        await db.flush()
        return existing
    row = ResellerPackagePrice(reseller_account_id=reseller_id, package_id=package_id, custom_price=price)
    db.add(row)
    await db.flush()
    return row


async def remove_custom_price(db: AsyncSession, *, reseller_id: UUID, package_id: UUID) -> None:
    existing = (await db.execute(
        select(ResellerPackagePrice).where(
            ResellerPackagePrice.reseller_account_id == reseller_id, ResellerPackagePrice.package_id == package_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.flush()


async def list_custom_prices(db: AsyncSession, *, reseller_id: UUID) -> list[ResellerPackagePrice]:
    return (await db.execute(select(ResellerPackagePrice).where(ResellerPackagePrice.reseller_account_id == reseller_id))).scalars().all()


async def list_resellers(db: AsyncSession) -> list[ResellerAccount]:
    return (await db.execute(select(ResellerAccount).order_by(ResellerAccount.created_at.desc()))).scalars().all()


async def toggle_status(db: AsyncSession, *, reseller_id: UUID) -> ResellerAccount:
    account = await db.get(ResellerAccount, reseller_id)
    account.status = "REVOKED" if account.status == "ACTIVE" else "ACTIVE"
    await db.flush()
    return account


# ===================================================================== AUTH
async def get_by_telegram_id(db: AsyncSession, *, telegram_id: int) -> ResellerAccount | None:
    return (await db.execute(select(ResellerAccount).where(ResellerAccount.telegram_id == telegram_id))).scalar_one_or_none()


async def deactivate_session(db: AsyncSession, *, reseller_id: UUID) -> None:
    account = await db.get(ResellerAccount, reseller_id)
    if account is not None:
        account.session_active = False
        await db.flush()


async def authenticate(db: AsyncSession, *, username: str, password: str, telegram_id: int) -> ResellerAccount:
    account = (await db.execute(select(ResellerAccount).where(ResellerAccount.username == username.strip()))).scalar_one_or_none()
    if account is None or not verify_password(password, account.password_hash):
        raise ResellerAuthError(internal_detail=f"bad credentials for username {username!r}")
    if account.status != "ACTIVE":
        raise ResellerRevokedError(internal_detail=f"reseller {account.username} is revoked")
    if account.telegram_id is not None and account.telegram_id != telegram_id:
        raise ResellerAlreadyBoundError(internal_detail=f"reseller {account.username} already bound to another telegram id")

    if account.telegram_id is None:
        account.telegram_id = telegram_id
        account.bound_at = datetime.now(timezone.utc)
    account.session_active = True
    await db.flush()
    return account


# ================================================================= PRICING
async def get_base_price(db: AsyncSession, *, telegram_id: int, package: Package) -> Decimal:
    """Returns the price to use BEFORE VIP/promo discounts: the reseller's price if this
    telegram_id is a currently-logged-in reseller, otherwise the normal customer price."""
    account = await get_by_telegram_id(db, telegram_id=telegram_id)
    if account is None or account.status != "ACTIVE" or not account.session_active:
        return package.selling_price

    if account.pricing_method == "FLAT_PERCENT":
        pct = account.flat_discount_percent or Decimal("0")
        return (package.selling_price * (Decimal("100") - pct) / Decimal("100")).quantize(Decimal("0.01"))

    # CUSTOM
    row = (await db.execute(
        select(ResellerPackagePrice).where(
            ResellerPackagePrice.reseller_account_id == account.id, ResellerPackagePrice.package_id == package.id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise ResellerPriceNotSetError(internal_detail=f"no custom price set for reseller {account.username} / package {package.id}")
    return row.custom_price


async def is_active_reseller_session(db: AsyncSession, *, telegram_id: int) -> bool:
    account = await get_by_telegram_id(db, telegram_id=telegram_id)
    return account is not None and account.status == "ACTIVE" and account.session_active


async def visible_packages_for(db: AsyncSession, *, telegram_id: int, all_packages: list[Package]) -> list[Package]:
    """For a CUSTOM-pricing reseller, hide packages that have no custom price set yet.
    Everyone else (customers, FLAT_PERCENT resellers) see every active package."""
    account = await get_by_telegram_id(db, telegram_id=telegram_id)
    if account is None or account.status != "ACTIVE" or not account.session_active or account.pricing_method != "CUSTOM":
        return all_packages

    priced_ids = {
        row.package_id for row in (await db.execute(
            select(ResellerPackagePrice).where(ResellerPackagePrice.reseller_account_id == account.id)
        )).scalars().all()
    }
    return [p for p in all_packages if p.id in priced_ids]

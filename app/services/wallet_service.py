"""
Every wallet balance change in the system MUST go through credit_wallet / debit_wallet.
Both use SELECT ... FOR UPDATE row locking so concurrent requests for the same wallet
(e.g. a double-tapped "Confirm Purchase" button) cannot race each other, and both write
a WalletTransaction row so balance_before/after is always auditable.
"""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Wallet, WalletTransaction, TransactionType, TransactionDirection
from app.core.exceptions import InsufficientBalanceError


async def get_or_create_wallet(db: AsyncSession, user_id: UUID) -> Wallet:
    result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        wallet = Wallet(user_id=user_id, balance=Decimal("0"))
        db.add(wallet)
        await db.flush()
    return wallet


async def _lock_wallet(db: AsyncSession, user_id: UUID) -> Wallet:
    """Row-level lock for the duration of the current transaction."""
    result = await db.execute(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    )
    wallet = result.scalar_one_or_none()
    if wallet is None:
        wallet = Wallet(user_id=user_id, balance=Decimal("0"))
        db.add(wallet)
        await db.flush()
        result = await db.execute(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        wallet = result.scalar_one()
    return wallet


async def credit_wallet(
    db: AsyncSession,
    *,
    user_id: UUID,
    amount: Decimal,
    txn_type: TransactionType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
    created_by_admin_telegram_id: int | None = None,
) -> Wallet:
    if amount <= 0:
        raise ValueError("credit amount must be positive")

    wallet = await _lock_wallet(db, user_id)
    before = wallet.balance
    wallet.balance = before + amount

    if txn_type == TransactionType.DEPOSIT:
        wallet.total_deposit += amount
    elif txn_type == TransactionType.REFERRAL_BONUS:
        wallet.total_referral_income += amount
    elif txn_type == TransactionType.REFUND:
        wallet.total_refund += amount

    wallet.version += 1

    db.add(WalletTransaction(
        wallet_id=wallet.id,
        type=txn_type,
        direction=TransactionDirection.CREDIT,
        amount=amount,
        balance_before=before,
        balance_after=wallet.balance,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        created_by_admin_telegram_id=created_by_admin_telegram_id,
    ))
    await db.flush()
    return wallet


async def debit_wallet(
    db: AsyncSession,
    *,
    user_id: UUID,
    amount: Decimal,
    txn_type: TransactionType,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
    created_by_admin_telegram_id: int | None = None,
) -> Wallet:
    if amount <= 0:
        raise ValueError("debit amount must be positive")

    wallet = await _lock_wallet(db, user_id)
    if wallet.balance < amount:
        raise InsufficientBalanceError(
            internal_detail=f"wallet {wallet.id} balance {wallet.balance} < debit {amount}"
        )

    before = wallet.balance
    wallet.balance = before - amount

    if txn_type == TransactionType.PURCHASE:
        wallet.total_purchase += amount

    wallet.version += 1

    db.add(WalletTransaction(
        wallet_id=wallet.id,
        type=txn_type,
        direction=TransactionDirection.DEBIT,
        amount=amount,
        balance_before=before,
        balance_after=wallet.balance,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        created_by_admin_telegram_id=created_by_admin_telegram_id,
    ))
    await db.flush()
    return wallet

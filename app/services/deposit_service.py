from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Deposit, DepositStatus, TransactionType, AdminLog
from app.services import wallet_service, referral_service
from app.core.security import generate_deposit_number
from app.core.exceptions import AppError


async def create_deposit(
    db: AsyncSession, *, user_id: UUID, payment_method_id: UUID, amount: Decimal,
    sender_number: str | None, transaction_reference: str,
) -> Deposit:
    deposit = Deposit(
        deposit_number=generate_deposit_number(),
        user_id=user_id,
        payment_method_id=payment_method_id,
        amount=amount,
        sender_number=sender_number,
        transaction_reference=transaction_reference,
        status=DepositStatus.PENDING,
    )
    db.add(deposit)
    try:
        await db.flush()
    except IntegrityError:
        raise AppError(
            internal_detail=f"duplicate transaction_reference {transaction_reference!r} for payment_method {payment_method_id}",
            user_message="❌ এই Transaction ID/Reference দিয়ে ইতিমধ্যে একটি ডিপোজিট জমা দেওয়া হয়েছে। ভুল হলে সঠিক Reference দিয়ে আবার চেষ্টা করুন, অথবা সাপোর্টে যোগাযোগ করুন।",
        )
    return deposit


async def approve_deposit(db: AsyncSession, *, deposit_id: UUID, admin_telegram_id: int) -> Deposit:
    deposit = (await db.execute(select(Deposit).where(Deposit.id == deposit_id).with_for_update())).scalar_one_or_none()
    if deposit is None:
        raise AppError(internal_detail="deposit not found", user_message="ডিপোজিট খুঁজে পাওয়া যায়নি।")
    if deposit.status != DepositStatus.PENDING:
        raise AppError(internal_detail="deposit already reviewed", user_message="এই ডিপোজিট ইতিমধ্যে প্রসেস করা হয়েছে।")

    deposit.status = DepositStatus.APPROVED
    deposit.reviewed_by_admin_telegram_id = admin_telegram_id
    from datetime import datetime, timezone
    deposit.reviewed_at = datetime.now(timezone.utc)

    await wallet_service.credit_wallet(
        db,
        user_id=deposit.user_id,
        amount=deposit.amount,
        txn_type=TransactionType.DEPOSIT,
        reference_type="deposit",
        reference_id=str(deposit.id),
        note=f"Deposit approved: {deposit.deposit_number}",
        created_by_admin_telegram_id=admin_telegram_id,
    )

    db.add(AdminLog(
        admin_telegram_id=admin_telegram_id, action="APPROVE_DEPOSIT", target_type="deposit", target_id=str(deposit.id),
        old_value={"status": "PENDING"}, new_value={"status": "APPROVED"},
    ))

    # First-deposit referral bonus, if configured and applicable.
    await referral_service.maybe_pay_referral_bonus(db, user_id=deposit.user_id, deposit_amount=deposit.amount)

    await db.flush()
    return deposit


async def reject_deposit(
    db: AsyncSession, *, deposit_id: UUID, admin_telegram_id: int, reason: str | None,
) -> tuple[Deposit, bool]:
    """Returns (deposit, newly_flagged) -- newly_flagged is True only the moment a user
    crosses the fraud threshold from this rejection, so the caller can notify admins once."""
    deposit = (await db.execute(select(Deposit).where(Deposit.id == deposit_id).with_for_update())).scalar_one_or_none()
    if deposit is None:
        raise AppError(internal_detail="deposit not found", user_message="ডিপোজিট খুঁজে পাওয়া যায়নি।")
    if deposit.status != DepositStatus.PENDING:
        raise AppError(internal_detail="deposit already reviewed", user_message="এই ডিপোজিট ইতিমধ্যে প্রসেস করা হয়েছে।")

    deposit.status = DepositStatus.REJECTED
    deposit.admin_note = reason
    deposit.reviewed_by_admin_telegram_id = admin_telegram_id
    from datetime import datetime, timezone
    deposit.reviewed_at = datetime.now(timezone.utc)

    db.add(AdminLog(
        admin_telegram_id=admin_telegram_id, action="REJECT_DEPOSIT", target_type="deposit", target_id=str(deposit.id),
        old_value={"status": "PENDING"}, new_value={"status": "REJECTED", "reason": reason},
    ))
    await db.flush()

    from app.services import fraud_service
    newly_flagged = await fraud_service.check_deposit_fraud(db, user_id=deposit.user_id)

    return deposit, newly_flagged

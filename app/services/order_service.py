"""
Implements the order sequence:

  1. User authentication            (caller passes an already-resolved User)
  2. Package active check
  3. UID validation                 (via provider adapter)
  4. Player Name confirmation       (returned to caller before order creation)
  5. Wallet balance check
  6. Order lock (idempotency key = unique constraint on orders.idempotency_key)
  7. Wallet amount deduct
  8. Provider order create
  9. Provider response save
  10. Webhook/status tracking       (see app/webhooks/router.py)
  11. Completed -> finalize
  12. Permanent failure -> refund

Steps 6-9 run inside one DB transaction per attempt so a crash between "wallet debited"
and "provider order created" always leaves an inspectable, retryable Order row instead of
silently losing money.
"""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Order, OrderLog, OrderStatus, Package, ProviderProduct, ApiProvider,
    TransactionType, User,
)
from app.providers.registry import get_adapter
from app.services import wallet_service, loyalty_service
from app.core.security import generate_order_number, generate_idempotency_key
from app.core.exceptions import (
    PackageInactiveError, ValidationError, IdempotencyConflictError,
    ProviderUnavailableError, OrderNotFoundError,
)


async def validate_uid_for_package(db: AsyncSession, *, package_id: UUID, uid: str) -> tuple[str, ProviderProduct, ApiProvider]:
    """Runs Player Validation against the package's active provider and returns
    (player_name, provider_product, provider)."""
    package = (await db.execute(select(Package).where(Package.id == package_id))).scalar_one_or_none()
    if package is None or not package.is_active:
        raise PackageInactiveError(internal_detail=f"package {package_id} inactive or missing")

    pp_result = await db.execute(
        select(ProviderProduct)
        .where(ProviderProduct.package_id == package_id, ProviderProduct.is_active == True)  # noqa: E712
        .join(ApiProvider)
        .where(ApiProvider.is_active == True)  # noqa: E712
        .order_by(ApiProvider.priority.asc())
    )
    provider_product = pp_result.scalars().first()
    if provider_product is None:
        raise ProviderUnavailableError(internal_detail=f"no active provider_product for package {package_id}")

    provider = (await db.execute(select(ApiProvider).where(ApiProvider.id == provider_product.provider_id))).scalar_one()
    adapter = get_adapter(provider)

    result = await adapter.validate_player(uid, region=package.region, product_id=provider_product.provider_product_id)
    if not result.valid:
        raise ValidationError(
            internal_detail=f"{provider.name} validation failed: {result.error_code} {result.error_message}"
        )
    return result.player_name, provider_product, provider


async def create_order(
    db: AsyncSession,
    *,
    user: User,
    package: Package,
    uid: str,
    player_name: str,
    provider_product: ProviderProduct,
    provider: ApiProvider,
    final_price: Decimal | None = None,
    discount_amount: Decimal = Decimal("0"),
    promo_code: str | None = None,
    vip_discount_percent: Decimal | None = None,
) -> Order:
    """Executes steps 5-9. Raises InsufficientBalanceError / IdempotencyConflictError /
    ProviderUnavailableError on failure. On provider failure the order row is still
    persisted with status=FAILED and the wallet debit is rolled back within this call.

    final_price/discount_amount/promo_code/vip_discount_percent let the caller apply a
    VIP tier discount and/or a promo code before the wallet is charged; the *base*
    package.selling_price is still what's used to build the idempotency key so the
    duplicate-order guard doesn't depend on which discounts happened to be active."""

    charge_price = final_price if final_price is not None else package.selling_price

    idempotency_key = generate_idempotency_key(
        "order", str(user.id), str(package.id), uid, str(package.selling_price)
    )

    existing = (await db.execute(select(Order).where(Order.idempotency_key == idempotency_key))).scalar_one_or_none()
    if existing is not None:
        if existing.status in (OrderStatus.PENDING, OrderStatus.PROCESSING):
            raise IdempotencyConflictError(internal_detail=f"order still in-flight, existing order {existing.order_number}")
        if existing.status == OrderStatus.COMPLETED:
            raise IdempotencyConflictError(internal_detail=f"duplicate of completed order {existing.order_number}")
        # FAILED / CANCELED: that attempt is over and (if it debited the wallet) was refunded,
        # so the same user+package+UID+price combination must be allowed to try again --
        # count every previous attempt (original + past retries) sharing this base key so
        # each new retry gets its own fresh, never-before-used key.
        prior_attempts = (await db.execute(
            select(func.count()).select_from(Order).where(Order.idempotency_key.like(f"{idempotency_key}%"))
        )).scalar_one()
        idempotency_key = f"{idempotency_key}-r{prior_attempts + 1}"

    order = Order(
        order_number=generate_order_number(),
        user_id=user.id,
        package_id=package.id,
        game_uid=uid,
        player_name=player_name,
        product_name_snapshot=package.name,
        selling_price=charge_price,
        provider_id=provider.id,
        provider_product_id=provider_product.provider_product_id,
        provider_cost_snapshot=provider_product.provider_cost,
        status=OrderStatus.PENDING,
        idempotency_key=idempotency_key,
        promo_code=promo_code,
        discount_amount=discount_amount,
        vip_discount_percent=vip_discount_percent,
    )
    db.add(order)
    try:
        await db.flush()  # enforce unique constraint on idempotency_key at the DB level too
    except IntegrityError:
        await db.rollback()
        raise IdempotencyConflictError(internal_detail="idempotency_key unique constraint hit")

    db.add(OrderLog(order_id=order.id, event="ORDER_CREATED", detail={
        "idempotency_key": idempotency_key, "promo_code": promo_code, "discount_amount": str(discount_amount),
    }))

    # Step 6/7: reserve funds BEFORE calling the provider so the user can never be charged
    # by the provider without their wallet reflecting it, even if we crash right after this line.
    await wallet_service.debit_wallet(
        db,
        user_id=user.id,
        amount=charge_price,
        txn_type=TransactionType.PURCHASE,
        reference_type="order",
        reference_id=str(order.id),
        note=f"Purchase: {package.name} for UID {uid}",
    )
    order.wallet_deducted = True
    order.status = OrderStatus.PROCESSING
    await db.flush()

    # Step 8: call the provider
    adapter = get_adapter(provider)
    order.attempt_count += 1
    try:
        result = await adapter.create_order(
            provider_product_id=provider_product.provider_product_id,
            uid=uid,
            idempotency_key=idempotency_key,
            region=package.region,
        )
    except Exception as exc:  # noqa: BLE001 - provider/network failure must not crash the order flow
        db.add(OrderLog(order_id=order.id, event="PROVIDER_CALL_EXCEPTION", detail={"error": str(exc)}))
        await _fail_and_refund(db, order, code="SERVICE_ERROR", message="provider request failed")
        return order

    # Step 9: persist provider response
    db.add(OrderLog(order_id=order.id, event="PROVIDER_ORDER_RESPONSE", detail=result.raw_response or {}))

    if not result.success:
        await _fail_and_refund(db, order, code=result.error_code or "SERVICE_ERROR", message=result.error_message or "order failed")
        return order

    order.provider_order_id = result.provider_order_id
    order.status = OrderStatus(result.status) if result.status in OrderStatus.__members__ else OrderStatus.PROCESSING
    await loyalty_service.maybe_award_points(db, order=order)
    await db.flush()
    return order


async def _fail_and_refund(db: AsyncSession, order: Order, *, code: str, message: str) -> None:
    order.status = OrderStatus.FAILED
    order.error_code = code
    order.error_message = message
    if order.wallet_deducted and not order.refunded:
        await wallet_service.credit_wallet(
            db,
            user_id=order.user_id,
            amount=order.selling_price,
            txn_type=TransactionType.REFUND,
            reference_type="order",
            reference_id=str(order.id),
            note=f"Auto-refund for failed order {order.order_number}",
        )
        order.refunded = True
    db.add(OrderLog(order_id=order.id, event="ORDER_FAILED_REFUNDED", detail={"code": code, "message": message}))
    await db.flush()


def format_order_card(order: Order) -> str:
    """Single source of truth for how an order looks in a Telegram message, used both
    right after purchase and when the polling service edits the same message in place
    as the status changes."""
    status_emoji = {
        "COMPLETED": "🟢", "PROCESSING": "🟡", "PENDING": "🟡", "FAILED": "🔴", "CANCELED": "🔴",
    }.get(order.status.value, "🟡")
    status_label_bn = {
        "COMPLETED": "সম্পন্ন", "PROCESSING": "প্রসেসিং হচ্ছে", "PENDING": "পেন্ডিং",
        "FAILED": "ব্যর্থ", "CANCELED": "বাতিল",
    }.get(order.status.value, order.status.value)

    lines = [
        f"📦 Order #{order.order_number}",
        f"💎 {order.product_name_snapshot}",
        f"🆔 UID: {order.game_uid}",
        f"👤 {order.player_name or '-'}",
    ]
    if order.discount_amount and order.discount_amount > 0:
        original = order.selling_price + order.discount_amount
        lines.append(f"💵 মূল্য: ৳{original:.0f} → ছাড়ের পর ৳{order.selling_price:.0f}")
        discount_bits = []
        if order.vip_discount_percent:
            discount_bits.append(f"VIP {order.vip_discount_percent:.0f}%")
        if order.promo_code:
            discount_bits.append(f"প্রোমো '{order.promo_code}'")
        if discount_bits:
            lines.append(f"🏷️ ছাড়: {' + '.join(discount_bits)}")
    else:
        lines.append(f"💰 ৳{order.selling_price:.0f}")
    lines.append(f"{status_emoji} Status: {status_label_bn}")
    if order.loyalty_points_earned:
        lines.append(f"🎯 +{order.loyalty_points_earned} লয়্যালটি পয়েন্ট অর্জিত")
    if order.status == OrderStatus.FAILED or order.status == OrderStatus.CANCELED:
        lines.append(f"⚠️ কারণ: {order.error_message or 'অজানা কারণ'}")
        if order.refunded:
            lines.append("💸 টাকা আপনার ওয়ালেটে ফেরত দেওয়া হয়েছে।")
    return "\n".join(lines)


async def apply_status_update(db: AsyncSession, *, order: Order, new_status: OrderStatus, raw: dict | None = None) -> None:
    """Called from the webhook handler and from admin manual retry/status polling.
    Idempotent: re-applying the same terminal status is a no-op; only transitions into
    FAILED/CANCELED trigger a refund, and only once (guarded by order.refunded)."""
    if order.status == new_status:
        return

    previous = order.status
    order.status = new_status
    db.add(OrderLog(order_id=order.id, event="STATUS_UPDATE", detail={"from": previous.value, "to": new_status.value, "raw": raw}))

    if new_status in (OrderStatus.FAILED, OrderStatus.CANCELED):
        if not order.error_message:
            d = (raw or {}).get("data", raw or {})
            err = d.get("error") if isinstance(d, dict) else None
            order.error_message = (err.get("message") if isinstance(err, dict) else None) or "প্রোভাইডার থেকে অর্ডার প্রক্রিয়া ব্যর্থ হয়েছে।"
        if order.wallet_deducted and not order.refunded:
            await wallet_service.credit_wallet(
                db,
                user_id=order.user_id,
                amount=order.selling_price,
                txn_type=TransactionType.REFUND,
                reference_type="order",
                reference_id=str(order.id),
                note=f"Refund for {new_status.value.lower()} order {order.order_number}",
            )
            order.refunded = True

    await loyalty_service.maybe_award_points(db, order=order)
    await db.flush()


async def retry_failed_order(db: AsyncSession, *, order_id: UUID, admin_telegram_id: int) -> Order | None:
    """Used by the Admin bot's "🔄 Retry" action. Re-validates the UID and places a brand
    new order (new order_number, new idempotency_key) for the same user/package/UID; the
    original FAILED order row is left untouched for audit history."""
    from app.models import AdminLog, User

    original = await db.get(Order, order_id)
    if original is None or original.status != OrderStatus.FAILED:
        return None

    provider_product = (await db.execute(
        select(ProviderProduct).where(
            ProviderProduct.package_id == original.package_id, ProviderProduct.is_active == True  # noqa: E712
        )
    )).scalars().first()
    if provider_product is None:
        return None

    package = await db.get(Package, original.package_id)
    user = await db.get(User, original.user_id)
    provider = await db.get(ApiProvider, provider_product.provider_id)

    player_name, provider_product, provider = await validate_uid_for_package(
        db, package_id=package.id, uid=original.game_uid
    )
    new_order = await create_order(
        db, user=user, package=package, uid=original.game_uid, player_name=player_name,
        provider_product=provider_product, provider=provider,
    )
    db.add(AdminLog(
        admin_telegram_id=admin_telegram_id, action="RETRY_ORDER", target_type="order", target_id=str(original.id),
        new_value={"new_order_id": str(new_order.id), "new_order_number": new_order.order_number},
    ))
    return new_order


async def get_order_by_provider_order_id(db: AsyncSession, *, provider_id: UUID, provider_order_id: str) -> Order:
    result = await db.execute(
        select(Order).where(Order.provider_id == provider_id, Order.provider_order_id == provider_order_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise OrderNotFoundError(internal_detail=f"no order for provider {provider_id} order_id {provider_order_id}")
    return order

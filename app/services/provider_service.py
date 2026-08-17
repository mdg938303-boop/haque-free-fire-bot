from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiProvider, AdminLog
from app.providers.registry import get_adapter, ADAPTER_REGISTRY
from app.core.security import encrypt_secret, mask_secret
from app.core.exceptions import AppError


def available_provider_codes() -> list[str]:
    """Codes the admin can pick from when adding a provider -- i.e. every adapter that
    currently has code written for it. New codes appear here automatically once
    registered in providers/registry.py."""
    return list(ADAPTER_REGISTRY.keys())


async def create_provider(
    db: AsyncSession, *, admin_telegram_id: int, name: str, code: str, base_url: str, api_key: str,
    auth_type: str = "bearer", auth_header_name: str | None = None,
    validation_endpoint: str | None = None, order_endpoint: str | None = None,
    status_endpoint: str | None = None, balance_endpoint: str | None = None,
    webhook_secret: str | None = None, extra_config: dict | None = None,
    priority: int = 100, is_active: bool = True,
) -> ApiProvider:
    if code not in ADAPTER_REGISTRY:
        raise AppError(
            internal_detail=f"unknown provider code {code}",
            user_message=f"'{code}' এর জন্য কোনো adapter কোডে রেজিস্টার করা নেই। Developer-কে জানান।",
        )
    provider = ApiProvider(
        name=name, code=code, base_url=base_url,
        api_key_encrypted=encrypt_secret(api_key),
        auth_type=auth_type, auth_header_name=auth_header_name,
        validation_endpoint=validation_endpoint, order_endpoint=order_endpoint,
        status_endpoint=status_endpoint, balance_endpoint=balance_endpoint,
        webhook_secret_encrypted=encrypt_secret(webhook_secret) if webhook_secret else None,
        extra_config=extra_config or {}, priority=priority, is_active=is_active,
    )
    db.add(provider)
    await db.flush()
    db.add(AdminLog(admin_telegram_id=admin_telegram_id, action="CREATE_PROVIDER", target_type="api_provider",
                     target_id=str(provider.id), new_value={"name": name, "code": code}))
    return provider


async def delete_provider(db: AsyncSession, *, provider_id: UUID, admin_telegram_id: int) -> str:
    provider = await db.get(ApiProvider, provider_id)
    if provider is None:
        raise AppError(internal_detail="provider not found", user_message="Provider খুঁজে পাওয়া যায়নি।")
    name = provider.name
    db.add(AdminLog(admin_telegram_id=admin_telegram_id, action="DELETE_PROVIDER", target_type="api_provider",
                     target_id=str(provider.id), new_value={"name": name}))
    await db.delete(provider)
    await db.flush()
    return name


async def update_provider_field(
    db: AsyncSession, *, provider_id: UUID, admin_telegram_id: int, field: str, value: str,
) -> ApiProvider:
    provider = await db.get(ApiProvider, provider_id)
    if provider is None:
        raise AppError(internal_detail="provider not found", user_message="Provider খুঁজে পাওয়া যায়নি।")

    if field == "api_key":
        provider.api_key_encrypted = encrypt_secret(value)
    elif field == "priority":
        provider.priority = int(value) if value.isdigit() else provider.priority
    elif field in ("validation_endpoint", "order_endpoint", "status_endpoint", "balance_endpoint"):
        setattr(provider, field, None if value == "-" else value)
    elif field in ("name", "base_url"):
        setattr(provider, field, value)
    else:
        raise AppError(internal_detail=f"unknown editable field {field}", user_message="অজানা ফিল্ড।")

    db.add(AdminLog(admin_telegram_id=admin_telegram_id, action="UPDATE_PROVIDER", target_type="api_provider",
                     target_id=str(provider.id), new_value={field: value if field != "api_key" else "***"}))
    await db.flush()
    return provider


async def toggle_provider(db: AsyncSession, *, provider_id: UUID, admin_telegram_id: int) -> ApiProvider:
    provider = await db.get(ApiProvider, provider_id)
    if provider is None:
        raise AppError(internal_detail="provider not found")
    provider.is_active = not provider.is_active
    db.add(AdminLog(admin_telegram_id=admin_telegram_id, action="TOGGLE_PROVIDER", target_type="api_provider",
                     target_id=str(provider.id), new_value={"is_active": provider.is_active}))
    await db.flush()
    return provider


async def test_provider_connection(db: AsyncSession, *, provider_id: UUID) -> dict:
    provider = (await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))).scalar_one_or_none()
    if provider is None:
        raise AppError(internal_detail="provider not found")
    adapter = get_adapter(provider)
    try:
        balance = await adapter.get_balance()
        return {"ok": True, "balance": balance.balance, "currency": balance.currency}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def masked_api_key(provider: ApiProvider) -> str:
    from app.core.security import decrypt_secret
    try:
        return mask_secret(decrypt_secret(provider.api_key_encrypted))
    except Exception:  # noqa: BLE001
        return "••••••••"

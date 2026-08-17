"""
Registry mapping ApiProvider.code -> Adapter class.

Adding a brand-new provider (e.g. "Provider B") means:
  1. Write app/providers/provider_b.py implementing BaseProviderAdapter.
  2. Add one line to ADAPTER_REGISTRY below.
  3. Create the provider row from the Admin Panel (base URL, API key, endpoints, etc).

No other file in the system needs to change — order_service, webhook router, and the
Admin Panel all talk to providers only through get_adapter().
"""
from app.models import ApiProvider
from app.providers.base import BaseProviderAdapter, ProviderConfig
from app.providers.epinby import EpinByAdapter
from app.core.security import decrypt_secret

ADAPTER_REGISTRY: dict[str, type[BaseProviderAdapter]] = {
    "epinby": EpinByAdapter,
    # "provider_b": ProviderBAdapter,
    # "provider_c": ProviderCAdapter,
}


def get_adapter(provider: ApiProvider) -> BaseProviderAdapter:
    adapter_cls = ADAPTER_REGISTRY.get(provider.code)
    if adapter_cls is None:
        raise ValueError(
            f"No adapter registered for provider code '{provider.code}'. "
            f"Add it to ADAPTER_REGISTRY in app/providers/registry.py."
        )

    config = ProviderConfig(
        provider_id=str(provider.id),
        name=provider.name,
        base_url=provider.base_url,
        api_key=decrypt_secret(provider.api_key_encrypted),
        auth_type=provider.auth_type,
        auth_header_name=provider.auth_header_name,
        validation_endpoint=provider.validation_endpoint,
        order_endpoint=provider.order_endpoint,
        status_endpoint=provider.status_endpoint,
        balance_endpoint=provider.balance_endpoint,
        webhook_secret=decrypt_secret(provider.webhook_secret_encrypted) if provider.webhook_secret_encrypted else None,
        extra_config=provider.extra_config or {},
    )
    return adapter_cls(config)

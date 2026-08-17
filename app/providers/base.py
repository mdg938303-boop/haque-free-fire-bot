"""
Generic Provider Adapter Interface.

The rest of the system (order engine, webhook router, admin panel) only ever
talks to this interface. Adding a new Top-Up API provider means writing one
new adapter class and registering it in `registry.py` — no other code changes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    player_name: str | None = None
    raw_uid: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class OrderResult:
    success: bool
    provider_order_id: str | None = None
    status: str | None = None  # provider's raw status string
    error_code: str | None = None
    error_message: str | None = None
    raw_response: dict | None = None


@dataclass
class OrderStatusResult:
    status: str  # normalized: PENDING/PROCESSING/COMPLETED/FAILED/CANCELED
    provider_order_id: str | None = None
    raw_response: dict | None = None


@dataclass
class BalanceResult:
    balance: float
    currency: str = "BDT"
    raw_response: dict | None = None


class ProviderConfig:
    """Runtime configuration for an adapter instance, sourced from the api_providers DB row.
    Nothing here is hard-coded — everything comes from the Admin Panel."""

    def __init__(
        self,
        provider_id: str,
        name: str,
        base_url: str,
        api_key: str,
        auth_type: str = "bearer",
        auth_header_name: str | None = None,
        validation_endpoint: str | None = None,
        order_endpoint: str | None = None,
        status_endpoint: str | None = None,
        balance_endpoint: str | None = None,
        webhook_secret: str | None = None,
        extra_config: dict | None = None,
    ):
        self.provider_id = provider_id
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.auth_type = auth_type
        self.auth_header_name = auth_header_name or "Authorization"
        self.validation_endpoint = validation_endpoint
        self.order_endpoint = order_endpoint
        self.status_endpoint = status_endpoint
        self.balance_endpoint = balance_endpoint
        self.webhook_secret = webhook_secret
        self.extra_config = extra_config or {}


class BaseProviderAdapter(ABC):
    """Every concrete provider (EpinBy, Provider B, Provider C ...) subclasses this."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def validate_player(self, uid: str, region: str = "BD") -> ValidationResult:
        """Validate a game UID and return the player's in-game display name."""
        raise NotImplementedError

    @abstractmethod
    async def create_order(
        self, *, provider_product_id: str, uid: str, idempotency_key: str, region: str = "BD"
    ) -> OrderResult:
        """Place a top-up order with the provider. Must be safe to retry with the same
        idempotency_key without creating a duplicate order on the provider side (pass it
        through as the provider's own idempotency/reference field when supported)."""
        raise NotImplementedError

    @abstractmethod
    async def get_order_status(self, provider_order_id: str) -> OrderStatusResult:
        raise NotImplementedError

    @abstractmethod
    async def get_balance(self) -> BalanceResult:
        raise NotImplementedError

    @abstractmethod
    def verify_webhook_signature(self, payload_bytes: bytes, headers: dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse_webhook_event(self, payload: dict) -> OrderStatusResult:
        """Turn a provider's webhook payload into a normalized OrderStatusResult.
        Must also expose the provider's own event id for de-duplication via
        payload's own fields — the caller reads that separately."""
        raise NotImplementedError

    @staticmethod
    def normalize_status(raw_status: str, mapping: dict[str, str]) -> str:
        """Map a provider-specific status string to our internal OrderStatus values,
        using the `extra_config['status_map']` configured in the Admin Panel."""
        return mapping.get(raw_status.upper(), "PROCESSING")

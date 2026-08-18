"""
EpinBy.com adapter.

Implemented against Epinby's official public API docs (https://www.epinby.com/docs):

  Base URL   : https://www.epinby.com/api/v1
  Auth       : header  X-API-KEY: <api_key>
  Endpoints  : GET  /getMe
               POST /validate-player   {product_id, player_id, server_id?}
               POST /order             {product_id, qty, player_id, server_id?, callback_url?, callback_mode?}
                    headers: X-API-KEY, X-Idempotency-Key
               GET  /order/{id}
  Webhooks   : header X-GAMEX-Signature: sha256=<hmac>  (HMAC-SHA256 of raw body using the
               reseller's personal `webhook_secret`, obtained once via GET /getMe and stored
               encrypted as the provider's webhook_secret in the Admin Panel)
               header X-GAMEX-Event: order.status_changed   (present in "events" callback_mode)

The `Package.region` / provider_product extra fields are NOT required by Epinby for Free Fire —
`product_id` alone identifies the SKU. `server_id` is left unset for Free Fire orders.
"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.providers.base import (
    BaseProviderAdapter, ValidationResult, OrderResult, OrderStatusResult, BalanceResult,
)
from app.core.security import verify_hmac_signature

EPINBY_STATUS_MAP = {
    "PENDING": "PENDING",
    "PROCESSING": "PROCESSING",
    "COMPLETED": "COMPLETED",
    "CANCELED": "CANCELED",
    "FAILED": "FAILED",
}

_RETRYABLE = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError)


class EpinByAdapter(BaseProviderAdapter):
    def _headers(self, idempotency_key: str | None = None) -> dict:
        headers = {
            "X-API-KEY": self.config.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return headers

    def _client(self) -> httpx.AsyncClient:
        base = self.config.base_url or "https://www.epinby.com/api/v1"
        return httpx.AsyncClient(base_url=base, timeout=20.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
           retry=retry_if_exception_type(_RETRYABLE))
    async def validate_player(self, uid: str, region: str = "BD", product_id: str | None = None) -> ValidationResult:
        endpoint = self.config.validation_endpoint or "/validate-player"
        pid = product_id or self.config.extra_config.get("default_validation_product_id")
        if pid is None:
            return ValidationResult(
                valid=False, raw_uid=uid, error_code="NO_PRODUCT_ID",
                error_message="কোনো EpinBy Product ID পাওয়া যায়নি — এই Package-এর সাথে EpinBy Provider Product ID যুক্ত করা হয়নি।",
            )
        payload = {"product_id": int(pid) if str(pid).isdigit() else pid, "player_id": uid}
        async with self._client() as client:
            resp = await client.post(endpoint, headers=self._headers(), json=payload)
        data = resp.json()
        if resp.status_code == 200 and data.get("success"):
            d = data["data"]
            return ValidationResult(
                valid=True,
                player_name=d.get("player_name") or d.get("nickname"),
                raw_uid=uid,
            )
        err = data.get("error", {})
        return ValidationResult(
            valid=False,
            raw_uid=uid,
            error_code=err.get("code", "VALIDATION_ERROR"),
            error_message=err.get("message", "player validation failed"),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
           retry=retry_if_exception_type(_RETRYABLE))
    async def create_order(
        self, *, provider_product_id: str, uid: str, idempotency_key: str, region: str = "BD"
    ) -> OrderResult:
        endpoint = self.config.order_endpoint or "/order"
        callback_url = self.config.extra_config.get("callback_url")
        payload = {
            "product_id": int(provider_product_id),
            "qty": 1,
            "player_id": uid,
        }
        if callback_url:
            payload["callback_url"] = callback_url
            payload["callback_mode"] = self.config.extra_config.get("callback_mode", "events")

        async with self._client() as client:
            resp = await client.post(endpoint, headers=self._headers(idempotency_key), json=payload)
        data = resp.json()

        if resp.status_code == 200 and data.get("success"):
            d = data["data"]
            return OrderResult(
                success=True,
                provider_order_id=str(d.get("order_id")),
                status=self.normalize_status(d.get("status", "PENDING"), EPINBY_STATUS_MAP),
                raw_response=data,
            )
        err = data.get("error", {})
        return OrderResult(
            success=False,
            error_code=err.get("code", "SERVICE_ERROR"),
            error_message=err.get("message", "order creation failed"),
            raw_response=data,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
           retry=retry_if_exception_type(_RETRYABLE))
    async def get_order_status(self, provider_order_id: str) -> OrderStatusResult:
        endpoint = (self.config.status_endpoint or "/order/{id}").replace("{id}", provider_order_id)
        async with self._client() as client:
            resp = await client.get(endpoint, headers=self._headers())
        data = resp.json()
        d = data.get("data", {})
        raw_status = d.get("status", "PROCESSING")
        return OrderStatusResult(
            status=self.normalize_status(raw_status, EPINBY_STATUS_MAP),
            provider_order_id=provider_order_id,
            raw_response=data,
        )

    async def get_balance(self) -> BalanceResult:
        endpoint = self.config.balance_endpoint or "/getMe"
        async with self._client() as client:
            resp = await client.get(endpoint, headers=self._headers())
        data = resp.json()
        d = data.get("data", {})
        return BalanceResult(
            balance=float(d.get("balance", 0)),
            currency=d.get("currency", "USD"),
            raw_response=data,
        )

    def verify_webhook_signature(self, payload_bytes: bytes, headers: dict) -> bool:
        signature = headers.get("x-gamex-signature") or headers.get("X-GAMEX-Signature", "")
        if not self.config.webhook_secret:
            return False
        return verify_hmac_signature(self.config.webhook_secret, payload_bytes, signature)

    def parse_webhook_event(self, payload: dict) -> OrderStatusResult:
        raw_status = payload.get("status", "PROCESSING")
        return OrderStatusResult(
            status=self.normalize_status(raw_status, EPINBY_STATUS_MAP),
            provider_order_id=str(payload.get("order_id")),
            raw_response=payload,
        )

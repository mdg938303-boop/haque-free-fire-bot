from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "FreeFireTopUpBot"
    APP_ENV: str = "production"
    APP_SECRET_KEY: str
    APP_TIMEZONE: str = "Asia/Dhaka"
    CURRENCY: str = "BDT"

    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    TELEGRAM_BOT_TOKEN: str
    # Comma-separated Telegram numeric user IDs. Anyone in this list gets the admin menu
    # inside the bot -- this IS the admin authentication system now (no separate login).
    TELEGRAM_ADMIN_IDS: str = ""

    # Render (and most free hosts) require a web service to bind to $PORT and answer HTTP
    # requests, or the deploy is considered unhealthy. We run a tiny FastAPI app with just
    # a /health route for this purpose; Render injects PORT automatically.
    PORT: int = 8000

    FIELD_ENCRYPTION_KEY: str

    # How often (seconds) the background poller checks PENDING/PROCESSING orders against
    # each provider's get_order_status endpoint, since we are not using provider webhooks.
    ORDER_POLL_INTERVAL_SECONDS: int = 45

    @property
    def telegram_admin_id_list(self) -> List[int]:
        return [int(x) for x in self.TELEGRAM_ADMIN_IDS.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

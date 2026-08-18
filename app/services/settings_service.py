from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting

DEFAULTS = {
    "general": {"bot_name": "Free Fire Top-Up", "bot_username": "", "support_username": "support",
                "currency": "BDT", "maintenance_mode": False},
    "referral": {"enabled": False, "bonus_amount": "0", "min_deposit": "0"},
    "topup": {"order_timeout": 120, "retry_limit": 3, "auto_retry": False},
    "loyalty": {"cashback_percent": "0", "redeem_rate": "10"},  # redeem_rate = points needed per ৳1
}


async def get_setting(db: AsyncSession, key: str) -> dict:
    row = await db.get(Setting, key)
    if row is not None:
        return row.value
    return dict(DEFAULTS.get(key, {}))


async def upsert_setting(db: AsyncSession, key: str, value: dict) -> None:
    row = await db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    await db.flush()


async def ensure_defaults(db: AsyncSession) -> None:
    """Called once at startup so a fresh database always has usable settings rows."""
    for key, value in DEFAULTS.items():
        row = await db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
    await db.flush()

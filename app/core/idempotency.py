from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyKey


async def claim_idempotency_key(db: AsyncSession, *, key: str, scope: str, resource_id: str | None = None) -> bool:
    """Returns True if the key was successfully claimed (first use), False if it was
    already used (caller should treat the operation as a duplicate and skip it)."""
    existing = (await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(IdempotencyKey(key=key, scope=scope, resource_id=resource_id))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    return True

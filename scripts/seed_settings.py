"""
Optional. In normal use you never need to run this manually -- app/main.py already
creates tables and default settings automatically on every startup (see init_db() and
ensure_defaults() in the lifespan handler). This script exists only for people who *do*
have terminal access and want to seed the database without starting the full app.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import session_scope, init_db
from app.services.settings_service import ensure_defaults


async def main():
    await init_db()
    async with session_scope() as db:
        await ensure_defaults(db)
    print("✅ Tables created and default settings seeded. Message /admin to your bot from a TELEGRAM_ADMIN_IDS account.")


if __name__ == "__main__":
    asyncio.run(main())

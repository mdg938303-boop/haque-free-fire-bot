"""Run the Telegram bot as its own process:  python run_bot.py
(Keep this separate from `uvicorn app.main:app`, which serves the Admin Panel + webhooks.)
"""
import asyncio
from app.bot.bot import run_polling

if __name__ == "__main__":
    asyncio.run(run_polling())

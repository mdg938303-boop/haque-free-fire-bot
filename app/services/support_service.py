from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SupportTicket, SupportMessage
from app.core.exceptions import AppError


async def create_ticket(db: AsyncSession, *, user_id: UUID, sender_telegram_id: int, message: str) -> SupportTicket:
    subject = (message[:60] + "…") if len(message) > 60 else message
    ticket = SupportTicket(user_id=user_id, subject=subject, status="OPEN")
    db.add(ticket)
    await db.flush()
    db.add(SupportMessage(ticket_id=ticket.id, sender_type="user", sender_telegram_id=sender_telegram_id, message=message))
    await db.flush()
    return ticket


async def add_message(db: AsyncSession, *, ticket_id: UUID, sender_type: str, sender_telegram_id: int, message: str) -> SupportMessage:
    ticket = await db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise AppError(internal_detail="ticket not found", user_message="❌ টিকেট খুঁজে পাওয়া যায়নি।")
    if ticket.status == "CLOSED" and sender_type == "user":
        ticket.status = "OPEN"  # a user reply reopens a closed ticket
        ticket.closed_at = None
    ticket.updated_at = datetime.now(timezone.utc)
    msg = SupportMessage(ticket_id=ticket_id, sender_type=sender_type, sender_telegram_id=sender_telegram_id, message=message)
    db.add(msg)
    await db.flush()
    return msg


async def close_ticket(db: AsyncSession, *, ticket_id: UUID) -> SupportTicket:
    ticket = await db.get(SupportTicket, ticket_id)
    ticket.status = "CLOSED"
    ticket.closed_at = datetime.now(timezone.utc)
    await db.flush()
    return ticket


async def list_open_tickets(db: AsyncSession) -> list[SupportTicket]:
    return (await db.execute(
        select(SupportTicket).where(SupportTicket.status == "OPEN").order_by(SupportTicket.updated_at.asc())
    )).scalars().all()


async def list_user_tickets(db: AsyncSession, *, user_id: UUID, limit: int = 10) -> list[SupportTicket]:
    return (await db.execute(
        select(SupportTicket).where(SupportTicket.user_id == user_id).order_by(SupportTicket.updated_at.desc()).limit(limit)
    )).scalars().all()


async def get_ticket_with_messages(db: AsyncSession, *, ticket_id: UUID) -> tuple[SupportTicket | None, list[SupportMessage]]:
    ticket = await db.get(SupportTicket, ticket_id)
    if ticket is None:
        return None, []
    messages = (await db.execute(
        select(SupportMessage).where(SupportMessage.ticket_id == ticket_id).order_by(SupportMessage.created_at.asc())
    )).scalars().all()
    return ticket, messages

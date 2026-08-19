from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.config import get_settings
from app.database import session_scope
from app.services import support_service
from app.bot.states import SupportStates
from app.bot.keyboards import (
    cancel_kb, main_menu_kb, support_tickets_list_kb, support_ticket_detail_kb,
)
from app.bot.handlers.start import get_or_create_user

settings = get_settings()
router = Router(name="support")


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


def _thread_text(ticket, messages) -> str:
    lines = [f"🎫 <b>{ticket.subject}</b>\nস্ট্যাটাস: {'🟢 Open' if ticket.status == 'OPEN' else '⚪ Closed'}\n"]
    for m in messages:
        who = "👤 আপনি" if m.sender_type == "user" else "🛠️ Support"
        lines.append(f"{who} ({m.created_at.strftime('%d %b %H:%M')}):\n{m.message}")
    return "\n\n".join(lines)


@router.callback_query(F.data == "support_new_ticket")
async def new_ticket_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportStates.waiting_new_ticket_message)
    await callback.message.answer("💬 আপনার সমস্যাটি বিস্তারিত লিখুন:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(SupportStates.waiting_new_ticket_message, F.text)
async def new_ticket_save(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        ticket = await support_service.create_ticket(
            db, user_id=user.id, sender_telegram_id=message.from_user.id, message=message.text.strip(),
        )
        ticket_id, subject = ticket.id, ticket.subject
        uname = user.telegram_username or user.full_name or str(user.telegram_id)

    await message.answer(f"✅ টিকেট তৈরি হয়েছে (#{str(ticket_id)[:8]})। শীঘ্রই সাপোর্ট টিম উত্তর দেবে।", reply_markup=main_menu_kb())

    for admin_id in settings.telegram_admin_id_list:
        try:
            await bot.send_message(
                admin_id,
                f"🎫 <b>নতুন সাপোর্ট টিকেট</b>\n\nফ্রম: @{uname}\n{subject}\n\n/admin → 🎫 Support Tickets থেকে উত্তর দিন।",
                parse_mode="HTML",
            )
        except Exception:  # noqa: BLE001 - one admin's chat being unreachable must not block others
            continue


@router.callback_query(F.data == "support_my_tickets")
async def my_tickets(callback: CallbackQuery):
    async with session_scope() as db:
        user = await get_or_create_user(db, callback.from_user)
        tickets = await support_service.list_user_tickets(db, user_id=user.id)
    await callback.message.edit_text("📋 <b>আমার টিকেট</b>", parse_mode="HTML", reply_markup=support_tickets_list_kb(tickets))
    await callback.answer()


@router.callback_query(F.data.startswith("support_ticket_view:"))
async def view_ticket(callback: CallbackQuery):
    ticket_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        user = await get_or_create_user(db, callback.from_user)
        ticket, messages = await support_service.get_ticket_with_messages(db, ticket_id=ticket_id)
        if ticket is None or ticket.user_id != user.id:
            await callback.answer("❌ টিকেট খুঁজে পাওয়া যায়নি।", show_alert=True)
            return
        text = _thread_text(ticket, messages)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=support_ticket_detail_kb(ticket))
    await callback.answer()


@router.callback_query(F.data.startswith("support_reply:"))
async def reply_ticket_start(callback: CallbackQuery, state: FSMContext):
    ticket_id = callback.data.split(":", 1)[1]
    await state.set_state(SupportStates.waiting_ticket_reply)
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer("✍️ আপনার উত্তর লিখুন:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(SupportStates.waiting_ticket_reply, F.text)
async def reply_ticket_save(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    ticket_id = data["ticket_id"]

    async with session_scope() as db:
        user = await get_or_create_user(db, message.from_user)
        ticket, _ = await support_service.get_ticket_with_messages(db, ticket_id=ticket_id)
        if ticket is None or ticket.user_id != user.id:
            await message.answer("❌ টিকেট খুঁজে পাওয়া যায়নি।", reply_markup=main_menu_kb())
            return
        await support_service.add_message(
            db, ticket_id=ticket_id, sender_type="user", sender_telegram_id=message.from_user.id, message=message.text.strip(),
        )
        subject = ticket.subject

    await message.answer("✅ আপনার উত্তর পাঠানো হয়েছে।", reply_markup=main_menu_kb())
    for admin_id in settings.telegram_admin_id_list:
        try:
            await bot.send_message(admin_id, f"🎫 টিকেট আপডেট: {subject}\n\n/admin → 🎫 Support Tickets")
        except Exception:  # noqa: BLE001
            continue

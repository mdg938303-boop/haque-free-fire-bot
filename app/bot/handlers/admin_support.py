from aiogram import Router, F, Bot
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.config import get_settings
from app.database import session_scope
from app.models import User
from app.services import support_service, review_service
from app.bot.states import AdminSupportStates
from app.bot.keyboards import admin_menu_kb, admin_cancel_kb, admin_support_tickets_list_kb, admin_ticket_detail_kb

settings = get_settings()
router = Router(name="admin_support")


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.telegram_admin_id_list


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _thread_text(ticket, messages) -> str:
    lines = [f"🎫 <b>{ticket.subject}</b>\nস্ট্যাটাস: {'🟢 Open' if ticket.status == 'OPEN' else '⚪ Closed'}\n"]
    for m in messages:
        who = "👤 User" if m.sender_type == "user" else "🛠️ Admin"
        lines.append(f"{who} ({m.created_at.strftime('%d %b %H:%M')}):\n{m.message}")
    return "\n\n".join(lines)


@router.message(F.text == "🎫 Support Tickets")
async def ticket_list_menu(message: Message):
    async with session_scope() as db:
        tickets = await support_service.list_open_tickets(db)
    await message.answer("🎫 <b>Open Support Tickets</b>", parse_mode="HTML", reply_markup=admin_support_tickets_list_kb(tickets))


@router.callback_query(F.data == "adm_tkt_list")
async def ticket_list_cb(callback: CallbackQuery):
    async with session_scope() as db:
        tickets = await support_service.list_open_tickets(db)
    await callback.message.edit_text("🎫 <b>Open Support Tickets</b>", parse_mode="HTML", reply_markup=admin_support_tickets_list_kb(tickets))
    await callback.answer()


@router.callback_query(F.data.startswith("adm_tkt_v:"))
async def ticket_view(callback: CallbackQuery):
    ticket_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        ticket, messages = await support_service.get_ticket_with_messages(db, ticket_id=ticket_id)
        if ticket is None:
            await callback.answer("❌ টিকেট খুঁজে পাওয়া যায়নি।", show_alert=True)
            return
        text = _thread_text(ticket, messages)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_ticket_detail_kb(ticket))
    await callback.answer()


@router.callback_query(F.data.startswith("adm_tkt_reply:"))
async def ticket_reply_start(callback: CallbackQuery, state: FSMContext):
    ticket_id = callback.data.split(":", 1)[1]
    await state.set_state(AdminSupportStates.waiting_reply)
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer("✍️ আপনার উত্তর লিখুন:", reply_markup=admin_cancel_kb())
    await callback.answer()


@router.message(AdminSupportStates.waiting_reply, F.text)
async def ticket_reply_save(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    ticket_id = data["ticket_id"]

    async with session_scope() as db:
        ticket, _ = await support_service.get_ticket_with_messages(db, ticket_id=ticket_id)
        if ticket is None:
            await message.answer("❌ টিকেট খুঁজে পাওয়া যায়নি।", reply_markup=admin_menu_kb())
            return
        await support_service.add_message(
            db, ticket_id=ticket_id, sender_type="admin", sender_telegram_id=message.from_user.id, message=message.text.strip(),
        )
        user = await db.get(User, ticket.user_id)
        subject = ticket.subject
        user_telegram_id = user.telegram_id if user else None

    await message.answer("✅ উত্তর পাঠানো হয়েছে।", reply_markup=admin_menu_kb())
    if user_telegram_id:
        try:
            await bot.send_message(
                user_telegram_id,
                f"🎫 <b>সাপোর্ট থেকে উত্তর এসেছে</b>\n\n{subject}\n\n📋 আমার টিকেট → দেখুন সম্পূর্ণ কথোপকথন।",
                parse_mode="HTML",
            )
        except Exception:  # noqa: BLE001
            pass


@router.callback_query(F.data.startswith("adm_tkt_close:"))
async def ticket_close(callback: CallbackQuery, bot: Bot):
    ticket_id = callback.data.split(":", 1)[1]
    async with session_scope() as db:
        ticket = await support_service.close_ticket(db, ticket_id=ticket_id)
        user = await db.get(User, ticket.user_id)
        tickets = await support_service.list_open_tickets(db)
        user_telegram_id = user.telegram_id if user else None
        subject = ticket.subject

    await callback.message.edit_text(
        f"✅ টিকেট বন্ধ করা হয়েছে।\n\n🎫 <b>Open Support Tickets</b>", parse_mode="HTML",
        reply_markup=admin_support_tickets_list_kb(tickets),
    )
    await callback.answer("✅ Closed")
    if user_telegram_id:
        try:
            await bot.send_message(user_telegram_id, f"🎫 আপনার টিকেট বন্ধ করা হয়েছে: {subject}")
        except Exception:  # noqa: BLE001
            pass


# =================================================================== REVIEWS
@router.message(F.text == "⭐ Reviews")
async def reviews_menu(message: Message):
    async with session_scope() as db:
        avg, count = await review_service.get_average_rating(db)
        recent = await review_service.list_recent_reviews(db, limit=10)

    lines = [f"⭐ <b>Reviews</b>\n\nগড় রেটিং: {avg:.1f} / 5 ({count}টি রিভিউ থেকে)\n"]
    for r in recent:
        stars = "⭐" * r.rating
        line = f"{stars} — {r.created_at.strftime('%d %b')}"
        if r.comment:
            line += f"\n  💬 {r.comment}"
        lines.append(line)
    if not recent:
        lines.append("(এখনো কোনো রিভিউ আসেনি)")

    await message.answer("\n".join(lines), parse_mode="HTML")

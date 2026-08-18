from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from app.database import session_scope
from app.models import ApiProvider, ProviderProduct
from app.providers.registry import get_adapter
from app.bot.states import UidCheckStates
from app.bot.keyboards import cancel_kb, uid_valid_kb

router = Router(name="uid_check")


@router.message(F.text == "🔎 চেক UID")
async def start_uid_check(message: Message, state: FSMContext):
    await state.set_state(UidCheckStates.waiting_uid)
    await message.answer("🆔 আপনার Free Fire UID পাঠান", reply_markup=cancel_kb())


@router.message(UidCheckStates.waiting_uid, F.text)
async def process_uid_check(message: Message, state: FSMContext):
    uid = message.text.strip()
    if not uid.isdigit():
        await message.answer("❌ সঠিক UID দিন (শুধু সংখ্যা)।")
        return

    async with session_scope() as db:
        provider = (await db.execute(
            select(ApiProvider).where(ApiProvider.is_active == True).order_by(ApiProvider.priority.asc())  # noqa: E712
        )).scalars().first()
        sample_product = None
        if provider is not None:
            sample_product = (await db.execute(
                select(ProviderProduct)
                .where(ProviderProduct.provider_id == provider.id, ProviderProduct.is_active == True)  # noqa: E712
            )).scalars().first()

    await state.clear()

    if provider is None:
        await message.answer("⚠️ এই মুহূর্তে সেবাটি বন্ধ আছে। কিছুক্ষণ পর আবার চেষ্টা করুন।")
        return

    if sample_product is None:
        await message.answer(
            "⚠️ এখনো কোনো Package/Provider Product সেটআপ করা হয়নি, তাই UID যাচাই করা যাচ্ছে না। "
            "অ্যাডমিনকে জানান।"
        )
        return

    adapter = get_adapter(provider)
    result = await adapter.validate_player(uid, product_id=sample_product.provider_product_id)

    if result.valid:
        await message.answer(
            f"✅ UID Valid\n\n🆔 UID: {uid}\n👤 Player Name: {result.player_name}",
            reply_markup=uid_valid_kb(),
        )
    else:
        await message.answer("❌ UID যাচাই করা যায়নি।\n\nসঠিক UID দিয়ে আবার চেষ্টা করুন।")

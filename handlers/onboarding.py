"""
Module 1: Admin Channel Setup & Onboarding
- Bot kanalga admin sifatida qo'shilganda avtomatik ro'yxatga oladi
- /mychannels — ulangan kanallar paneli (auto-approve yoqish/o'chirish, welcome tahrirlash)
"""

import logging

import asyncpg
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, ADMINISTRATOR, IS_NOT_MEMBER
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated, Message, CallbackQuery

import database as db
from keyboards import ChannelCB, channels_list_kb, channel_dashboard_kb, start_menu_kb
from states import WelcomeSetup

logger = logging.getLogger("PlanningME_bot")
router = Router(name="onboarding")

# Bu routerdagi barcha message handlerlari FAQAT shaxsiy chatda ishlaydi.
# Sabab: bot guruhga/kanalga ?startgroup=true orqali qo'shilganda, Telegram avtomatik
# ravishda /start buyrug'ini o'sha chat ichida yuboradi — filtrsiz bu guruhga to'liq
# shaxsiy menyuni (inline+reply keyboard) chiqarib yuborardi.
router.message.filter(F.chat.type == "private")


REQUIRED_RIGHTS = ("can_invite_users", "can_post_messages", "can_delete_messages")

START_TEXT_TEMPLATE = (
    "Salom, <b>{full_name}</b>! 👋\n\n"
    "Men — kanal va guruhlaringiz uchun SMM/moderatsiya botiman. Imkoniyatlarim:\n\n"
    "📥 <b>Auto-approve</b> — kanalga qo'shilish so'rovlarini avtomatik tasdiqlayman\n"
    "✉️ <b>Welcome xabar</b> — yangi a'zolarga shaxsiy xabar yuboraman\n"
    "🗓 <b>Post rejalashtirish</b> — /newpost orqali kanalga postni oldindan belgilangan vaqtda joylashtiraman\n"
    "🛡 <b>Group Guard</b> — bog'langan guruhda spam/havolalarni avtomatik o'chiraman"
)


@router.message(CommandStart())
async def cmd_start(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    """Bot bilan birinchi tanishuv. Foydalanuvchini bazaga yozadi va inline menyu bilan javob beradi."""
    await db.upsert_user(
        db_pool, message.from_user.id, message.from_user.full_name, message.from_user.username
    )
    logger.info("👋 /start bosdi: %s (id=%s)", message.from_user.full_name, message.from_user.id)

    bot_info = await bot.get_me()
    await message.answer(
        START_TEXT_TEMPLATE.format(full_name=message.from_user.full_name),
        reply_markup=start_menu_kb(bot_info.username),
    )


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> ADMINISTRATOR))
async def bot_promoted_to_admin(event: ChatMemberUpdated, db_pool: asyncpg.Pool):
    """Bot biror kanal/guruhda administrator qilib tayinlanganda ishga tushadi."""
    new_member = event.new_chat_member
    missing_rights = [r for r in REQUIRED_RIGHTS if not getattr(new_member, r, False)]
    if missing_rights:
        logger.warning(
            "Bot %s kanalida admin bo'ldi, lekin huquqlar yetishmaydi: %s",
            event.chat.id, missing_rights,
        )
        # Huquqlar yetarli bo'lmasa ham kanalni ro'yxatga olamiz, lekin admin bilishi kerak
        try:
            await event.bot.send_message(
                event.from_user.id,
                f"⚠️ <b>{event.chat.title}</b> kanalida meni admin qildingiz, lekin quyidagi "
                f"huquqlar yetishmayapti: {', '.join(missing_rights)}.\n"
                f"To'liq ishlashim uchun ularni yoqib qo'ying.",
            )
        except Exception:
            pass  # foydalanuvchi botni PM'da bloklagan bo'lishi mumkin

    owner_id = event.from_user.id
    await db.upsert_user(db_pool, owner_id, event.from_user.full_name, event.from_user.username)
    await db.upsert_channel(db_pool, event.chat.id, owner_id, event.chat.title or "Noma'lum kanal")

    logger.info("✅ Kanal ro'yxatga olindi: %s (id=%s, owner=%s)", event.chat.title, event.chat.id, owner_id)
    try:
        await event.bot.send_message(
            owner_id,
            f"✅ <b>{event.chat.title}</b> muvaffaqiyatli ulandi!\n"
            f"Boshqarish uchun /mychannels buyrug'ini yuboring.",
        )
    except Exception:
        pass


async def _send_channels_list(db_pool: asyncpg.Pool, user_id: int, answer_func):
    """/mychannels buyrug'i va 📋 tezkor tugma bir xil natijani ko'rsatishi uchun umumiy logika."""
    channels = await db.get_user_channels(db_pool, user_id)
    if not channels:
        await answer_func(
            "Sizga tegishli kanallar topilmadi.\n"
            "Meni istalgan kanalingizga <b>administrator</b> qilib qo'shing — "
            "avtomatik ro'yxatga olinaman."
        )
        return
    await answer_func("📋 Sizning kanallaringiz:", reply_markup=channels_list_kb(channels))


@router.message(Command("mychannels"))
async def my_channels(message: Message, db_pool: asyncpg.Pool):
    await _send_channels_list(db_pool, message.from_user.id, message.answer)


@router.callback_query(F.data == "btn_mychannels")
async def btn_mychannels(callback: CallbackQuery, db_pool: asyncpg.Pool):
    await _send_channels_list(db_pool, callback.from_user.id, callback.message.answer)
    await callback.answer()


@router.callback_query(ChannelCB.filter(F.action == "back"))
async def back_to_channels(callback: CallbackQuery, db_pool: asyncpg.Pool):
    channels = await db.get_user_channels(db_pool, callback.from_user.id)
    await callback.message.edit_text("📋 Sizning kanallaringiz:", reply_markup=channels_list_kb(channels))
    await callback.answer()


@router.callback_query(ChannelCB.filter(F.action == "open"))
async def open_channel_dashboard(callback: CallbackQuery, callback_data: ChannelCB, db_pool: asyncpg.Pool):
    channel = await db.get_channel(db_pool, callback_data.channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.answer("Bu kanal sizga tegishli emas.", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚙️ <b>{channel['title']}</b> sozlamalari:",
        reply_markup=channel_dashboard_kb(channel),
    )
    await callback.answer()


@router.callback_query(ChannelCB.filter(F.action == "toggle"))
async def toggle_channel_auto_approve(callback: CallbackQuery, callback_data: ChannelCB, db_pool: asyncpg.Pool):
    channel = await db.get_channel(db_pool, callback_data.channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.answer("Bu kanal sizga tegishli emas.", show_alert=True)
        return
    new_value = await db.toggle_auto_approve(db_pool, callback_data.channel_id)
    channel = await db.get_channel(db_pool, callback_data.channel_id)
    await callback.message.edit_reply_markup(reply_markup=channel_dashboard_kb(channel))
    await callback.answer(f"Auto-approve endi {'yoqildi ✅' if new_value else 'o‘chirildi ❌'}")


@router.callback_query(ChannelCB.filter(F.action == "edit_welcome"))
async def start_edit_welcome(
    callback: CallbackQuery, callback_data: ChannelCB, state: FSMContext, db_pool: asyncpg.Pool
):
    channel = await db.get_channel(db_pool, callback_data.channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.answer("Bu kanal sizga tegishli emas.", show_alert=True)
        return
    await state.set_state(WelcomeSetup.waiting_text)
    await state.update_data(channel_id=callback_data.channel_id)
    await callback.message.answer(
        "✏️ Yangi welcome xabar matnini yuboring "
        "(yangi a'zolarga shaxsiy xabarda shu matn yuboriladi):"
    )
    await callback.answer()


@router.message(WelcomeSetup.waiting_text)
async def save_welcome_text(message: Message, state: FSMContext, db_pool: asyncpg.Pool):
    data = await state.get_data()
    channel_id = data["channel_id"]
    await db.set_welcome_message(db_pool, channel_id, message.text)
    await state.clear()
    await message.answer("✅ Welcome xabar saqlandi.")
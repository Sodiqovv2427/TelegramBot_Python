"""
Module 1: Admin Channel/Group Setup & Onboarding
- Bot kanal yoki guruhga admin sifatida qo'shilganda avtomatik ro'yxatga oladi
  (chat_type orqali 'channel' / 'group' sifatida ajratiladi)
- /mychats — ulangan kanallar va guruhlar paneli (auto-approve yoqish/o'chirish)
"""

import logging

import asyncpg
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, ADMINISTRATOR, IS_NOT_MEMBER
from aiogram.types import ChatMemberUpdated, Message, CallbackQuery

import database as db
from keyboards import ChannelCB, channels_list_kb, channel_dashboard_kb, start_menu_kb, main_menu_kb

logger = logging.getLogger("PlanningME_bot")
router = Router(name="onboarding")


# Kanal va guruh uchun talab qilinadigan huquqlar farq qiladi — guruhda "post_messages"
# tushunchasi yo'q, shu sabab alohida ro'yxatlarga bo'lingan.
CHANNEL_REQUIRED_RIGHTS = ("can_invite_users", "can_post_messages", "can_delete_messages")
GROUP_REQUIRED_RIGHTS = ("can_delete_messages", "can_invite_users")

START_TEXT_TEMPLATE = (
    "Salom, <b>{full_name}</b>! 👋\n\n"
    "Men — kanal va guruhlaringiz uchun SMM/moderatsiya botiman. Imkoniyatlarim:\n\n"
    "📥 <b>Auto-approve</b> — kanalga qo'shilish so'rovlarini avtomatik tasdiqlayman\n"
    "🗓 <b>Post rejalashtirish</b> — /newpost orqali kanalga postni oldindan belgilangan vaqtda joylashtiraman\n"
    "🛡 <b>Group Guard</b> — bog'langan guruhda spam/havolalarni avtomatik o'chiraman\n"
    "📣 <b>Broadcast</b> — (faqat adminlar) barcha ulangan kanal/guruhlarga e'lon yuboraman"
)

FAQ_TEXT = (
    "ℹ️ <b>Bot haqida qo'llanma</b>\n\n"
    "1️⃣ Meni istalgan kanal yoki guruhingizga <b>administrator</b> qilib qo'shing.\n"
    "2️⃣ Kanal/guruh avtomatik ro'yxatga olinadi — <code>📢 Mening kanallarim</code> yoki "
    "<code>💬 Mening guruhlarim</code> tugmasidan boshqaring.\n"
    "3️⃣ <b>Auto-approve</b>ni yoqsangiz, qo'shilish so'rovlari to'liq jim (sizga ham, "
    "foydalanuvchiga ham hech qanday PM/DM yuborilmasdan) tasdiqlanadi va bazaga yoziladi.\n"
    "4️⃣ <code>✍️ Yangi post (Kanalga)</code> orqali kanalingizga rejalashtirilgan post tuzing.\n"
    "5️⃣ Yangi a'zo qo'shilganda sizga (admin/egaga) shaxsiy xabar keladi — "
    "foydalanuvchining o'ziga esa hech qanday xabar yuborilmaydi.\n"
    "6️⃣ <code>🛡 Guruh Guard</code> — guruhlarda havola/mention/spam so'z bo'lgan xabarlarni "
    "avtomatik o'chiradi (adminlar bundan mustasno).\n"
    "7️⃣ <code>📣 Kanalga e'lon yuborish</code> / <code>💬 Guruhga e'lon yuborish</code> — "
    "faqat botning super-admini yoki tayinlangan adminlar uchun.\n\n"
    "Savollar bo'lsa — <code>⚙️ Sozlamalar</code> bo'limiga qarang."
)

COMING_SOON_TEXT = "🚧 Bu bo'lim hozircha ishlab chiqilmoqda. Tez orada qo'shiladi!"
COMING_SOON_BUTTONS = {
    "👥 Referal tizimi",
    "📊 Statistika (Botniki)",
    "⚙️ Sozlamalar",
}


@router.message(CommandStart())
async def cmd_start(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    """Bot bilan birinchi tanishuv. Foydalanuvchini bazaga yozadi va inline menyu bilan javob beradi."""
    await db.upsert_user(
        db_pool, message.from_user.id, message.from_user.full_name, message.from_user.username
    )
    logger.info("👋 /start bosdi: %s (id=%s)", message.from_user.full_name, message.from_user.id)

    bot_info = await bot.get_me()

    # Telegram bir xabarda faqat bitta reply_markup turini qabul qiladi (yo reply, yo inline),
    # shuning uchun ikkita ketma-ket xabar bilan bajaramiz:

    # 1) Doimiy (persistent) 3x3 reply keyboard — welcome matni bilan birga
    await message.answer(
        START_TEXT_TEMPLATE.format(full_name=message.from_user.full_name),
        reply_markup=main_menu_kb(),
    )

    # 2) Inline menyu — /start javobining tagida (kanal/guruhga qo'shish + tezkor amallar)
    await message.answer(
        "👇 Tezkor amallar:",
        reply_markup=start_menu_kb(bot_info.username),
    )


def _resolve_chat_type(telegram_chat_type: str) -> str:
    """Telegram chat.type ('channel' | 'group' | 'supergroup') -> bizning ichki 'channel'/'group'."""
    return "channel" if telegram_chat_type == "channel" else "group"


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> ADMINISTRATOR))
async def bot_promoted_to_admin(event: ChatMemberUpdated, db_pool: asyncpg.Pool):
    """Bot biror kanal/guruhda administrator qilib tayinlanganda ishga tushadi."""
    chat_type = _resolve_chat_type(event.chat.type)
    required_rights = CHANNEL_REQUIRED_RIGHTS if chat_type == "channel" else GROUP_REQUIRED_RIGHTS

    new_member = event.new_chat_member
    missing_rights = [r for r in required_rights if not getattr(new_member, r, False)]
    if missing_rights:
        logger.warning(
            "Bot %s (%s) da admin bo'ldi, lekin huquqlar yetishmaydi: %s",
            event.chat.id, chat_type, missing_rights,
        )
        # Huquqlar yetarli bo'lmasa ham ro'yxatga olamiz, lekin admin bilishi kerak
        try:
            await event.bot.send_message(
                event.from_user.id,
                f"⚠️ <b>{event.chat.title}</b> da meni admin qildingiz, lekin quyidagi "
                f"huquqlar yetishmayapti: {', '.join(missing_rights)}.\n"
                f"To'liq ishlashim uchun ularni yoqib qo'ying.",
            )
        except Exception:
            pass  # foydalanuvchi botni PM'da bloklagan bo'lishi mumkin

    owner_id = event.from_user.id
    await db.upsert_user(db_pool, owner_id, event.from_user.full_name, event.from_user.username)
    await db.upsert_channel(
        db_pool, event.chat.id, owner_id, event.chat.title or "Noma'lum", chat_type=chat_type
    )

    label = "Kanal" if chat_type == "channel" else "Guruh"
    logger.info(
        "✅ %s ro'yxatga olindi: %s (id=%s, owner=%s)", label, event.chat.title, event.chat.id, owner_id
    )
    try:
        await event.bot.send_message(
            owner_id,
            f"✅ <b>{event.chat.title}</b> ({label.lower()}) muvaffaqiyatli ulandi!\n"
            f"Boshqarish uchun /mychats buyrug'ini yuboring.",
        )
    except Exception:
        pass


async def _send_chat_list(
    db_pool: asyncpg.Pool, user_id: int, chat_type: str, answer_func
):
    """/mychats va reply-tugmalar (kanal/guruh) bir xil natijani ko'rsatishi uchun umumiy logika."""
    chats = await db.get_user_channels(db_pool, user_id, chat_type=chat_type)
    label = "kanal" if chat_type == "channel" else "guruh"
    if not chats:
        await answer_func(
            f"Sizga tegishli {label}lar topilmadi.\n"
            f"Meni istalgan {label}ingizga <b>administrator</b> qilib qo'shing — "
            f"avtomatik ro'yxatga olinaman."
        )
        return
    await answer_func(f"📋 Sizning {label}laringiz:", reply_markup=channels_list_kb(chats))


@router.message(Command("mychats"))
async def my_channels(message: Message, db_pool: asyncpg.Pool):
    # /mychats buyrug'i — kanallar va guruhlarni ikkita alohida ro'yxat sifatida ko'rsatamiz
    channels = await db.get_user_channels(db_pool, message.from_user.id, chat_type="channel")
    groups = await db.get_user_channels(db_pool, message.from_user.id, chat_type="group")

    if not channels and not groups:
        await message.answer(
            "Sizga tegishli kanal yoki guruh topilmadi.\n"
            "Meni istalgan kanal/guruhingizga <b>administrator</b> qilib qo'shing — "
            "avtomatik ro'yxatga olinaman."
        )
        return

    if channels:
        await message.answer("📢 Sizning kanallaringiz:", reply_markup=channels_list_kb(channels))
    if groups:
        await message.answer("💬 Sizning guruhlaringiz:", reply_markup=channels_list_kb(groups))


@router.message(F.text == "📢 Mening kanallarim")
async def reply_btn_mychannels(message: Message, db_pool: asyncpg.Pool):
    await _send_chat_list(db_pool, message.from_user.id, "channel", message.answer)


@router.message(F.text == "💬 Mening guruhlarim")
async def reply_btn_mygroups(message: Message, db_pool: asyncpg.Pool):
    await _send_chat_list(db_pool, message.from_user.id, "group", message.answer)


@router.callback_query(F.data == "btn_mychannels")
async def btn_mychannels(callback: CallbackQuery, db_pool: asyncpg.Pool):
    await _send_chat_list(db_pool, callback.from_user.id, "channel", callback.message.answer)
    await callback.answer()


@router.callback_query(F.data == "btn_faq")
async def btn_faq(callback: CallbackQuery):
    """/start ostidagi 'ℹ️ Bot haqida (FAQ)' inline tugmasi — bot qo'llanmasini ko'rsatadi."""
    await callback.message.answer(FAQ_TEXT)
    await callback.answer()


@router.callback_query(ChannelCB.filter(F.action == "back"))
async def back_to_channels(callback: CallbackQuery, db_pool: asyncpg.Pool):
    channels = await db.get_user_channels(db_pool, callback.from_user.id)
    await callback.message.edit_text("📋 Sizning kanal/guruhlaringiz:", reply_markup=channels_list_kb(channels))
    await callback.answer()


@router.callback_query(ChannelCB.filter(F.action == "open"))
async def open_channel_dashboard(callback: CallbackQuery, callback_data: ChannelCB, db_pool: asyncpg.Pool):
    channel = await db.get_channel(db_pool, callback_data.channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.answer("Bu sizga tegishli emas.", show_alert=True)
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
        await callback.answer("Bu sizga tegishli emas.", show_alert=True)
        return
    new_value = await db.toggle_auto_approve(db_pool, callback_data.channel_id)
    channel = await db.get_channel(db_pool, callback_data.channel_id)
    await callback.message.edit_reply_markup(reply_markup=channel_dashboard_kb(channel))
    await callback.answer(f"Auto-approve endi {'yoqildi ✅' if new_value else 'o‘chirildi ❌'}")


# ============ Hali ishlab chiqilmagan menyu bo'limlari uchun neytral javob ============
# (Referal tizimi / Statistika / Sozlamalar) — TZ ushbu bo'limlarni batafsil belgilamagan,
# shuning uchun tugma bosilganda foydalanuvchi "javobsiz qolib ketmasligi" uchun qo'yilgan.

@router.message(F.text.in_(COMING_SOON_BUTTONS))
async def coming_soon(message: Message):
    await message.answer(COMING_SOON_TEXT)
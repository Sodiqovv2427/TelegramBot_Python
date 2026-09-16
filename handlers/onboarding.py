"""
Module 1: Admin Channel Setup & Onboarding
- Bot kanalga admin sifatida qo'shilganda avtomatik ro'yxatga oladi
- /mychannels — ulangan kanallar paneli (auto-approve yoqish/o'chirish, welcome tahrirlash)
"""

import logging

import asyncpg
from aiogram import Router, F, Bot
from aiogram.filters import (
    Command, CommandStart, CommandObject, StateFilter,
    ChatMemberUpdatedFilter, ADMINISTRATOR, IS_NOT_MEMBER, IS_MEMBER,
)
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatMemberUpdated, Message, CallbackQuery

import database as db
from keyboards import (
    ChannelCB, channels_list_kb, channel_dashboard_kb, start_menu_kb, main_reply_keyboard,
)
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
async def cmd_start(message: Message, db_pool: asyncpg.Pool, bot: Bot, command: CommandObject):
    """Bot bilan birinchi tanishuv. Foydalanuvchini bazaga yozadi va menyular bilan javob beradi."""
    # Referal deep-link: https://t.me/<bot>?start=<referrer_id>
    referrer_id = None
    if command.args and command.args.isdigit():
        candidate = int(command.args)
        if candidate != message.from_user.id:
            referrer_id = candidate

    await db.upsert_user(
        db_pool, message.from_user.id, message.from_user.full_name, message.from_user.username,
        referrer_id=referrer_id,
    )
    logger.info("👋 /start bosdi: %s (id=%s)", message.from_user.full_name, message.from_user.id)

    bot_info = await bot.get_me()
    await message.answer(
        START_TEXT_TEMPLATE.format(full_name=message.from_user.full_name),
        reply_markup=start_menu_kb(bot_info.username),
    )

    await message.answer(
        "Pastki menyudan foydalanishingiz mumkin 👇",
        reply_markup=main_reply_keyboard(),
    )


@router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=(IS_MEMBER | IS_NOT_MEMBER) >> ADMINISTRATOR)
)
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

    # Bot o'zi qaysi chatga, qanday nom bilan qo'shilganini va nechta a'zo borligini aniqlaydi
    try:
        member_count = await event.bot.get_chat_member_count(event.chat.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        member_count = None

    owner_id = event.from_user.id
    await db.upsert_user(db_pool, owner_id, event.from_user.full_name, event.from_user.username)
    await db.upsert_channel(
        db_pool, event.chat.id, owner_id, event.chat.title or "Noma'lum kanal",
        chat_type=event.chat.type, member_count=member_count,
    )

    label = "kanal" if event.chat.type == "channel" else "guruh"
    logger.info(
        "✅ %s ro'yxatga olindi: %s (id=%s, owner=%s, a'zolar=%s)",
        label, event.chat.title, event.chat.id, owner_id, member_count,
    )

    # 1) Chatning O'ZIGA tabrik xabari (agar yozish huquqi bo'lsa)
    try:
        await event.bot.send_message(
            event.chat.id,
            "✅ Bot muvaffaqiyatli ulandi va ishga tayyor!\n"
            "Sozlamalar uchun botga shaxsiy xabar yozing (/mychannels).",
        )
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.info("Chatning o'ziga xabar yuborib bo'lmadi (huquq yo'q): %s", e)

    # 2) Egasiga (PM) tasdiqlash xabari — a'zolar soni bilan
    count_line = f"\n👥 A'zolar soni: <b>{member_count}</b>" if member_count is not None else ""
    try:
        await event.bot.send_message(
            owner_id,
            f"✅ <b>{event.chat.title}</b> ({label}) muvaffaqiyatli ulandi!{count_line}\n"
            f"Boshqarish uchun /mychannels buyrug'ini yuboring.",
        )
    except Exception:
        pass


async def _register_channel_if_admin(
    bot: Bot, db_pool: asyncpg.Pool, chat_id_or_username, requester_id: int,
    requester_name: str, requester_username: str | None,
) -> tuple[bool, str]:
    """
    Berilgan chat (ID yoki @username) uchun botning admin ekanligini tekshiradi va shunday bo'lsa
    ro'yxatga oladi. (ok, xabar) qaytaradi.
    """
    try:
        chat = await bot.get_chat(chat_id_or_username)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        return False, f"❌ Chat topilmadi: {e}"

    if chat.type not in ("channel", "group", "supergroup"):
        return False, "❌ Bu shaxsiy chat — faqat kanal yoki guruhni qo'shish mumkin."

    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        return False, f"❌ Bot holatini tekshirib bo'lmadi (bot u yerga umuman qo'shilmagan bo'lishi mumkin): {e}"

    if member.status != "administrator":
        return False, f"❌ Bot <b>{chat.title}</b>da administrator emas. Avval admin huquqini bering."

    try:
        member_count = await bot.get_chat_member_count(chat.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        member_count = None

    await db.upsert_user(db_pool, requester_id, requester_name, requester_username)
    await db.upsert_channel(
        db_pool, chat.id, requester_id, chat.title or str(chat.id),
        chat_type=chat.type, member_count=member_count,
    )
    logger.info("✅ Qo'lda ro'yxatga olindi: %s (id=%s, owner=%s)", chat.title, chat.id, requester_id)
    count_line = f"\n👥 A'zolar soni: <b>{member_count}</b>" if member_count is not None else ""
    return True, f"✅ <b>{chat.title}</b> muvaffaqiyatli ulandi!{count_line}"


@router.message(Command("addchannel"))
async def add_channel_cmd(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "Kanalingiz avtomatik ro'yxatga tushmagan bo'lsa, shu orqali qo'lda qo'shing:\n\n"
            "<code>/addchannel @kanal_username</code>\n\n"
            "Yoki kanal/guruhdan istalgan postni to'g'ridan-to'g'ri shu botga <b>forward</b> qiling."
        )
        return
    ok, text = await _register_channel_if_admin(
        bot, db_pool, parts[1].strip(),
        message.from_user.id, message.from_user.full_name, message.from_user.username,
    )
    await message.answer(text)


@router.message(StateFilter(None), F.forward_from_chat)
async def add_channel_via_forward(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    fwd_chat = message.forward_from_chat
    ok, text = await _register_channel_if_admin(
        bot, db_pool, fwd_chat.id,
        message.from_user.id, message.from_user.full_name, message.from_user.username,
    )
    await message.answer(text)


async def _send_channels_list(
    db_pool: asyncpg.Pool, user_id: int, answer_func, chat_type: str | None = None
):
    """
    /mychannels va "Mening kanallarim"/"Mening guruhlarim" tugmalari uchun umumiy logika.
    chat_type=None -> hammasi (kanal+guruh aralash), "channel" -> faqat kanallar, "group" -> faqat guruhlar.
    """
    if chat_type is None:
        channels = await db.get_user_channels_cached(db_pool, user_id)  # Cache-Aside misoli
        label, label_title = "kanal/guruh", "kanal va guruhlaringiz"
    else:
        channels = await db.get_user_channels_by_type(db_pool, user_id, chat_type)
        label = "kanal" if chat_type == "channel" else "guruh"
        label_title = "kanallaringiz" if chat_type == "channel" else "guruhlaringiz"

    if not channels:
        await answer_func(
            f"Sizga tegishli {label} topilmadi.\n\n"
            f"Meni istalgan {label}ingizga <b>administrator</b> qilib qo'shing — avtomatik ro'yxatga olinaman.\n\n"
            f"Agar allaqachon admin qilib qo'shgan bo'lsangiz-u, shu yerda ko'rinmasa — "
            f"<code>/addchannel @username</code> buyrug'idan yoki u yerdan bir postni shu botga "
            f"forward qilishdan foydalaning."
        )
        return
    await answer_func(f"📋 Sizning {label_title}:", reply_markup=channels_list_kb(channels))


@router.message(Command("mychannels"))
async def my_channels(message: Message, db_pool: asyncpg.Pool):
    await _send_channels_list(db_pool, message.from_user.id, message.answer)


@router.message(F.text == "📢 Mening kanallarim")
async def reply_kb_only_channels(message: Message, db_pool: asyncpg.Pool):
    await _send_channels_list(db_pool, message.from_user.id, message.answer, chat_type="channel")


@router.message(F.text == "💬 Mening guruhlarim")
async def reply_kb_only_groups(message: Message, db_pool: asyncpg.Pool):
    await _send_channels_list(db_pool, message.from_user.id, message.answer, chat_type="group")


@router.callback_query(ChannelCB.filter(F.action == "back"))
async def back_to_channels(callback: CallbackQuery, db_pool: asyncpg.Pool):
    channels = await db.get_user_channels(db_pool, callback.from_user.id)
    await callback.message.edit_text("📋 Sizning kanal va guruhlaringiz:", reply_markup=channels_list_kb(channels))
    await callback.answer()


@router.callback_query(ChannelCB.filter(F.action == "open"))
async def open_channel_dashboard(callback: CallbackQuery, callback_data: ChannelCB, db_pool: asyncpg.Pool):
    channel = await db.get_channel(db_pool, callback_data.channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.answer("Bu kanal sizga tegishli emas.", show_alert=True)
        return
    count_line = f"\n👥 A'zolar soni: <b>{channel['member_count']}</b>" if channel["member_count"] else ""
    await callback.message.edit_text(
        f"⚙️ <b>{channel['title']}</b> sozlamalari:{count_line}",
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


# ============ Pastki reply-keyboard tugmalari ============

@router.message(F.text == "📊 Analitika")
async def reply_kb_analytics(message: Message, db_pool: asyncpg.Pool):
    stats = await db.get_user_analytics(db_pool, message.from_user.id)
    await message.answer(
        "📊 <b>Sizning statistikangiz</b>\n\n"
        f"📢 Kanallar: <b>{stats['channels_count']}</b> ta\n"
        f"💬 Guruhlar: <b>{stats['groups_count']}</b> ta\n"
        f"👤 Jami a'zolar (kanal+guruhlaringizda): <b>{stats['total_members']}</b> ta\n"
        f"👥 Bot orqali qo'shilganlar (join so'rovi): <b>{stats['total_joins']}</b> ta\n"
        f"🗓 Rejalashtirilgan postlar (kutilmoqda): <b>{stats['posts_scheduled']}</b> ta\n"
        f"✅ Yuborilgan postlar: <b>{stats['posts_published']}</b> ta"
    )


@router.message(F.text == "⚙️ Sozlamalar")
async def reply_kb_settings(message: Message):
    await message.answer(
        "⚙️ <b>Sozlamalar</b>\n\n"
        "Har bir kanal/guruh sozlamalari alohida boshqariladi — /mychannels orqali kerakli "
        "kanalni tanlang, u yerda quyidagilarni o'zgartira olasiz:\n\n"
        "• <b>Auto-approve</b> — qo'shilish so'rovlarini avtomatik tasdiqlash (yoqish/o'chirish)\n"
        "• <b>Welcome xabar</b> — yangi a'zoga shaxsiy yuboriladigan matnni tahrirlash"
    )


@router.message(F.text == "👥 Referal")
async def reply_kb_referral(message: Message, db_pool: asyncpg.Pool, bot: Bot):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    count = await db.count_referrals(db_pool, message.from_user.id)
    await message.answer(
        f"👥 <b>Do'stlaringizni taklif qiling</b>\n\n"
        f"Sizning shaxsiy havolangiz:\n<code>{ref_link}</code>\n\n"
        f"📊 Siz orqali botga qo'shilganlar: <b>{count}</b> ta"
    )


@router.message(F.text == "ℹ️ Yordam")
async def reply_kb_help(message: Message):
    await message.answer(
        "ℹ️ <b>Yordam — tugmalar nima qiladi</b>\n\n"
        "📢 <b>Mening kanallarim</b> — ulangan kanallaringiz ro'yxati; har birini bosib "
        "auto-approve va welcome xabarni sozlashingiz mumkin\n\n"
        "💬 <b>Mening guruhlarim</b> — ulangan guruhlaringiz ro'yxati, xuddi shu sozlamalar bilan\n\n"
        "📤 <b>Kanalga / Guruhga post yuborish</b> — tanlangan bitta kanal yoki guruhga, "
        "belgilangan vaqtda (masalan 1 soatdan keyin) chiqadigan, ixtiyoriy inline tugmali "
        "post rejalashtirish\n\n"
        "📊 <b>Analitika</b> — kanal/guruhlaringiz, a'zolar va postlar bo'yicha statistika\n\n"
        "👥 <b>Referal</b> — do'stlaringizni botga taklif qilish havolasi va statistikasi\n\n"
        "⚙️ <b>Sozlamalar</b> — har bir kanalning auto-approve/welcome sozlamalarini boshqarish\n\n"
        "<b>Buyruqlar:</b>\n"
        "/start — botni qayta ishga tushirish\n"
        "/mychannels — barcha ulangan kanal va guruhlaringiz (aralash ro'yxat)\n"
        "/newpost — yangi post rejalashtirish\n"
        "/addchannel @username — kanalni qo'lda ro'yxatga qo'shish (avtomatik ishlamasa)\n\n"
        "<b>Boshlash uchun:</b> meni kanalingizga yoki guruhingizga <b>administrator</b> qilib qo'shing."
    )
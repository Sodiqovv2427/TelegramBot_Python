"""
Module 3: Scheduled Post & Inline Keyboard Builder (FSM)

Oqim: /newpost -> kanal tanlash -> kontent -> (ixtiyoriy) tugmalar -> vaqt -> tasdiqlash
"""

import logging
import re
from datetime import datetime, timedelta

import asyncpg
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import database as db
from keyboards import (
    NewPostChannelCB,
    NewPostTypeCB,
    PostConfirmCB,
    CHANNEL_NEWPOST_BTN,
    GROUP_NEWPOST_BTN,
    newpost_type_kb,
    channels_choice_kb,
    post_confirm_kb,
    build_post_inline_keyboard,
    inline_keyboard_to_json,
)
from states import PostCreation

logger = logging.getLogger("PlanningME_bot")
router = Router(name="post_scheduler")

# Post yaratish oqimi faqat shaxsiy chatda boshlanishi va davom etishi kerak (guruh/kanalda emas)
router.message.filter(F.chat.type == "private")

RELATIVE_TIME_RE = re.compile(r"^in\s+(\d+)\s*(m|min|h|hour|d|day)s?$", re.IGNORECASE)


def parse_publish_time(raw: str) -> datetime | None:
    """
    Ikki formatni qo'llab-quvvatlaydi:
      - Aniq vaqt: "2026-09-15 18:30"
      - Nisbiy vaqt: "in 30m", "in 2h", "in 1d"
    Noto'g'ri format bo'lsa None qaytaradi.
    """
    raw = raw.strip()

    match = RELATIVE_TIME_RE.match(raw)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        if unit.startswith("m"):
            delta = timedelta(minutes=amount)
        elif unit.startswith("h"):
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(days=amount)
        return datetime.now() + delta

    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


async def _start_new_post(state: FSMContext, answer_func):
    """/newpost buyrug'i uchun — avval kanalgami yoki guruhgami ekanini so'raydi."""
    await state.set_state(PostCreation.choosing_type)
    await answer_func("📢 Postni qayerga joylashtirmoqchisiz?", reply_markup=newpost_type_kb())


@router.message(Command("newpost"))
async def start_new_post(message: Message, state: FSMContext):
    await _start_new_post(state, message.answer)


async def _show_channels_for_post(
    db_pool: asyncpg.Pool, user_id: int, chat_type: str, state: FSMContext, answer_func
):
    """Tur allaqachon ma'lum bo'lganda (pastki tugma orqali) to'g'ridan-to'g'ri kanal/guruh ro'yxatini ko'rsatadi."""
    channels = await db.get_user_channels_by_type(db_pool, user_id, chat_type)
    label = "kanal" if chat_type == "channel" else "guruh"

    if not channels:
        await answer_func(
            f"Sizda ulangan {label} topilmadi.\n\n"
            f"Avval botni {label}ingizga <b>administrator</b> qilib qo'shing, yoki agar allaqachon "
            f"qo'shgan bo'lsangiz-u, ro'yxatga tushmagan bo'lsa — /addchannel buyrug'idan foydalaning."
        )
        return

    await state.set_state(PostCreation.choosing_channel)
    await answer_func(f"📢 Qaysi {label}ga post joylashtiramiz?", reply_markup=channels_choice_kb(channels))


@router.message(F.text == CHANNEL_NEWPOST_BTN)
async def reply_kb_newpost_channel(message: Message, state: FSMContext, db_pool: asyncpg.Pool):
    await _show_channels_for_post(db_pool, message.from_user.id, "channel", state, message.answer)


@router.message(F.text == GROUP_NEWPOST_BTN)
async def reply_kb_newpost_group(message: Message, state: FSMContext, db_pool: asyncpg.Pool):
    await _show_channels_for_post(db_pool, message.from_user.id, "group", state, message.answer)


@router.callback_query(PostCreation.choosing_type, NewPostTypeCB.filter())
async def post_type_chosen(
    callback: CallbackQuery, callback_data: NewPostTypeCB, state: FSMContext, db_pool: asyncpg.Pool
):
    chat_type = callback_data.chat_type
    channels = await db.get_user_channels_by_type(db_pool, callback.from_user.id, chat_type)
    label = "kanal" if chat_type == "channel" else "guruh"

    if not channels:
        await callback.message.edit_text(
            f"Sizda ulangan {label} topilmadi.\n\n"
            f"Avval botni {label}ingizga <b>administrator</b> qilib qo'shing, yoki agar allaqachon "
            f"qo'shgan bo'lsangiz-u, ro'yxatga tushmagan bo'lsa — /addchannel buyrug'idan foydalaning."
        )
        await callback.answer()
        return

    await state.set_state(PostCreation.choosing_channel)
    await callback.message.edit_text(
        f"📢 Qaysi {label}ga post joylashtiramiz?", reply_markup=channels_choice_kb(channels)
    )
    await callback.answer()


@router.callback_query(PostCreation.choosing_channel, NewPostChannelCB.filter())
async def post_channel_chosen(callback: CallbackQuery, callback_data: NewPostChannelCB, state: FSMContext):
    await state.update_data(channel_id=callback_data.channel_id)
    await state.set_state(PostCreation.waiting_content)
    await callback.message.edit_text(
        "✍️ Post matnini yuboring (matn, rasm, video yoki fayl — izoh bilan bo'lishi mumkin)."
    )
    await callback.answer()


@router.message(PostCreation.waiting_content, F.text | F.photo | F.video | F.document)
async def post_content_received(message: Message, state: FSMContext):
    if message.photo:
        media_id, media_type, text = message.photo[-1].file_id, "photo", message.caption
    elif message.video:
        media_id, media_type, text = message.video.file_id, "video", message.caption
    elif message.document:
        media_id, media_type, text = message.document.file_id, "document", message.caption
    else:
        media_id, media_type, text = None, None, message.text

    await state.update_data(content_text=text, media_id=media_id, media_type=media_type)
    await state.set_state(PostCreation.waiting_buttons)
    await message.answer(
        "🔘 Inline tugmalar qo'shmoqchimisiz?\n\n"
        "Har bir tugmani alohida qatorda shu formatda yuboring:\n"
        "<code>Tugma matni - https://havola.com</code>\n\n"
        "Tugma kerak bo'lmasa, <b>o'tkazib yuborish</b> uchun /skip yuboring."
    )


@router.message(PostCreation.waiting_buttons, Command("skip"))
async def skip_buttons(message: Message, state: FSMContext):
    await state.update_data(inline_keyboard=None)
    await _ask_publish_time(message, state)


@router.message(PostCreation.waiting_buttons, F.text)
async def buttons_received(message: Message, state: FSMContext):
    lines = [line for line in message.text.split("\n") if line.strip()]
    markup = build_post_inline_keyboard(lines)
    if markup is None:
        await message.answer(
            "❌ Format tushunilmadi. Namuna: <code>Bizning sayt - https://example.com</code>\n"
            "Yoki /skip yuboring."
        )
        return
    await state.update_data(inline_keyboard=inline_keyboard_to_json(markup))
    await _ask_publish_time(message, state)


async def _ask_publish_time(message: Message, state: FSMContext):
    await state.set_state(PostCreation.waiting_time)
    await message.answer(
        "🕒 Nashr qilinadigan vaqtni kiriting:\n\n"
        "• Aniq vaqt: <code>2026-09-15 18:30</code>\n"
        "• Nisbiy vaqt: <code>in 30m</code>, <code>in 2h</code>, <code>in 1d</code>"
    )


@router.message(PostCreation.waiting_time, F.text)
async def publish_time_received(message: Message, state: FSMContext):
    publish_at = parse_publish_time(message.text)
    if publish_at is None:
        await message.answer(
            "❌ Vaqt formati tushunilmadi. Namuna: <code>2026-09-15 18:30</code> yoki <code>in 30m</code>"
        )
        return
    if publish_at <= datetime.now():
        await message.answer("❌ Vaqt kelajakda bo'lishi kerak. Qaytadan kiriting.")
        return

    await state.update_data(publish_at=publish_at.isoformat())
    data = await state.get_data()
    await state.set_state(PostCreation.confirm)

    preview = data.get("content_text") or "(matnsiz, faqat media)"
    await message.answer(
        f"📋 <b>Post tayyor — tekshiring:</b>\n\n"
        f"{preview}\n\n"
        f"🕒 Nashr vaqti: <b>{publish_at.strftime('%Y-%m-%d %H:%M')}</b>\n"
        f"🔘 Tugmalar: {'bor' if data.get('inline_keyboard') else 'yo‘q'}",
        reply_markup=post_confirm_kb(),
    )


@router.callback_query(PostCreation.confirm, PostConfirmCB.filter(F.action == "cancel"))
async def cancel_post(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Post bekor qilindi.")
    await callback.answer()


@router.callback_query(PostCreation.confirm, PostConfirmCB.filter(F.action == "confirm"))
async def confirm_post(callback: CallbackQuery, state: FSMContext, db_pool: asyncpg.Pool):
    data = await state.get_data()
    post_id = await db.create_scheduled_post(
        db_pool,
        channel_id=data["channel_id"],
        content_text=data.get("content_text"),
        media_id=data.get("media_id"),
        media_type=data.get("media_type"),
        inline_keyboard=data.get("inline_keyboard"),
        publish_at=datetime.fromisoformat(data["publish_at"]),
    )
    await state.clear()
    logger.info("📝 Yangi post rejalashtirildi: post_id=%s channel_id=%s", post_id, data["channel_id"])
    await callback.message.edit_text(f"✅ Post #{post_id} rejalashtirildi!")
    await callback.answer()
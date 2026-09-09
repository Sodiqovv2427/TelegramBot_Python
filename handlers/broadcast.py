"""
Module 5: Broadcast / E'lon yuborish (Admin-only)

TZ talabi: "📣 Kanalga e'lon yuborish" va "💬 Guruhga e'lon yuborish" faqat quyidagilarga ruxsat:
  - Super Admin — .env dagi ADMIN_ID
  - Bazadagi bot_admins jadvaliga super admin tomonidan qo'shilgan qo'shimcha adminlar
Oddiy foydalanuvchilar bu tugmalarni bossa, aniq rad javobi olishadi va hech qanday
broadcast oqimi boshlanmaydi.

Oqim:
  1) Admin tugmani bosadi -> ruxsat tekshiriladi
  2) Ruxsat bo'lsa -> "Xabaringizni yuboring" (matn/rasm/video/fayl — barchasi qo'llab-quvvatlanadi,
     chunki copy_message orqali ASL formatda ko'chiriladi)
  3) Admin kontent yuboradi -> nechta manzilga ketishi ko'rsatiladi -> Ha/Yo'q tasdiqlash
  4) Tasdiqlansa -> barcha ro'yxatdan o'tgan kanal (yoki guruh)larga copy_message orqali yuboriladi,
     muvaffaqiyatli/xatolik sonlari hisoblanib, admin'ga hisobot beriladi.

Qo'shimcha buyruqlar (FAQAT super admin uchun):
  /addadmin <user_id>    — bazaga admin qo'shadi
  /removeadmin <user_id> — bazadan adminni o'chiradi
  /admins                — joriy adminlar ro'yxati
"""

import logging

import asyncpg
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import database as db
from config import config
from keyboards import BroadcastConfirmCB, broadcast_confirm_kb
from states import BroadcastStates

logger = logging.getLogger("PlanningME_bot")
router = Router(name="broadcast")

CHANNEL_BUTTON_TEXT = "📣 Kanalga e'lon yuborish"
GROUP_BUTTON_TEXT = "💬 Guruhga e'lon yuborish"

ACCESS_DENIED_TEXT = (
    "⛔ Kechirasiz, bu bo'lim faqat botning administratorlari uchun.\n"
    "Agar bu xato deb hisoblasangiz, super admin bilan bog'laning."
)


async def _is_authorized(db_pool: asyncpg.Pool, user_id: int) -> bool:
    """Super admin (.env ADMIN_ID) YOKI bazadagi bot_admins ro'yxatidagi foydalanuvchi."""
    if config.admin_id and user_id == config.admin_id:
        return True
    return await db.is_bot_admin(db_pool, user_id)


def _is_super_admin(user_id: int) -> bool:
    return bool(config.admin_id) and user_id == config.admin_id


# ============ Broadcast boshlash ============

@router.message(F.text == CHANNEL_BUTTON_TEXT)
async def start_channel_broadcast(message: Message, state: FSMContext, db_pool: asyncpg.Pool):
    if not await _is_authorized(db_pool, message.from_user.id):
        await message.answer(ACCESS_DENIED_TEXT)
        return
    targets = await db.get_all_chats(db_pool, chat_type="channel")
    if not targets:
        await message.answer("❌ Hozircha ro'yxatdan o'tgan kanal yo'q.")
        return
    await state.set_state(BroadcastStates.waiting_content)
    await state.update_data(target_type="channel")
    await message.answer(
        f"📣 <b>Kanalga e'lon</b>\n\n"
        f"Yubormoqchi bo'lgan xabaringizni yuboring (matn, rasm, video yoki fayl — "
        f"caption bilan bo'lishi mumkin). Bu <b>{len(targets)}</b> ta ulangan kanalga yuboriladi.\n\n"
        f"Bekor qilish uchun /cancel yuboring."
    )


@router.message(F.text == GROUP_BUTTON_TEXT)
async def start_group_broadcast(message: Message, state: FSMContext, db_pool: asyncpg.Pool):
    if not await _is_authorized(db_pool, message.from_user.id):
        await message.answer(ACCESS_DENIED_TEXT)
        return
    targets = await db.get_all_chats(db_pool, chat_type="group")
    if not targets:
        await message.answer("❌ Hozircha ro'yxatdan o'tgan guruh yo'q.")
        return
    await state.set_state(BroadcastStates.waiting_content)
    await state.update_data(target_type="group")
    await message.answer(
        f"💬 <b>Guruhga e'lon</b>\n\n"
        f"Yubormoqchi bo'lgan xabaringizni yuboring (matn, rasm, video yoki fayl — "
        f"caption bilan bo'lishi mumkin). Bu <b>{len(targets)}</b> ta ulangan guruhga yuboriladi.\n\n"
        f"Bekor qilish uchun /cancel yuboring."
    )


@router.message(BroadcastStates.waiting_content, Command("cancel"))
@router.message(BroadcastStates.confirm, Command("cancel"))
async def cancel_broadcast_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Broadcast bekor qilindi.")


@router.message(BroadcastStates.waiting_content)
async def broadcast_content_received(message: Message, state: FSMContext, db_pool: asyncpg.Pool):
    data = await state.get_data()
    target_type = data["target_type"]
    targets = await db.get_all_chats(db_pool, chat_type=target_type)

    await state.update_data(source_chat_id=message.chat.id, source_message_id=message.message_id)
    await state.set_state(BroadcastStates.confirm)

    label = "kanal" if target_type == "channel" else "guruh"
    await message.answer(
        f"📋 Xabaringiz tayyor. <b>{len(targets)}</b> ta {label}ga yuborilsinmi?",
        reply_markup=broadcast_confirm_kb(len(targets)),
    )


@router.callback_query(BroadcastStates.confirm, BroadcastConfirmCB.filter(F.action == "cancel"))
async def broadcast_cancel_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Broadcast bekor qilindi.")
    await callback.answer()


@router.callback_query(BroadcastStates.confirm, BroadcastConfirmCB.filter(F.action == "confirm"))
async def broadcast_confirm_cb(callback: CallbackQuery, state: FSMContext, db_pool: asyncpg.Pool):
    data = await state.get_data()
    target_type = data["target_type"]
    source_chat_id = data["source_chat_id"]
    source_message_id = data["source_message_id"]

    targets = await db.get_all_chats(db_pool, chat_type=target_type)
    await state.clear()

    await callback.message.edit_text(f"⏳ Yuborilmoqda... (0/{len(targets)})")

    success, failed = 0, 0
    for chat in targets:
        try:
            await callback.bot.copy_message(
                chat_id=chat["channel_id"],
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            success += 1
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            failed += 1
            logger.warning(
                "Broadcast xatolik: chat=%s xato=%s", chat["channel_id"], e
            )

    label = "kanal" if target_type == "channel" else "guruh"
    await callback.message.answer(
        f"✅ <b>Broadcast yakunlandi</b>\n\n"
        f"📤 Yuborildi: {success} ta {label}ga\n"
        f"❌ Xatolik: {failed} ta"
    )
    await callback.answer()
    logger.info(
        "📣 Broadcast (%s) tugadi: admin=%s success=%s failed=%s",
        target_type, callback.from_user.id, success, failed,
    )


# ============ Super-admin: bot_admins boshqaruvi ============

@router.message(Command("addadmin"))
async def add_admin_cmd(message: Message, db_pool: asyncpg.Pool):
    if not _is_super_admin(message.from_user.id):
        return  # oddiy foydalanuvchilarga bu buyruq borligini ham bildirmaymiz

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer("Foydalanish: <code>/addadmin USER_ID</code>")
        return

    new_admin_id = int(parts[1].strip())
    await db.add_bot_admin(db_pool, new_admin_id, added_by=message.from_user.id)
    await message.answer(f"✅ <code>{new_admin_id}</code> admin sifatida qo'shildi.")


@router.message(Command("removeadmin"))
async def remove_admin_cmd(message: Message, db_pool: asyncpg.Pool):
    if not _is_super_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer("Foydalanish: <code>/removeadmin USER_ID</code>")
        return

    target_id = int(parts[1].strip())
    removed = await db.remove_bot_admin(db_pool, target_id)
    if removed:
        await message.answer(f"✅ <code>{target_id}</code> adminlikdan olib tashlandi.")
    else:
        await message.answer(f"ℹ️ <code>{target_id}</code> admin ro'yxatida topilmadi.")


@router.message(Command("admins"))
async def list_admins_cmd(message: Message, db_pool: asyncpg.Pool):
    if not _is_super_admin(message.from_user.id):
        return

    admins = await db.list_bot_admins(db_pool)
    lines = [f"👑 Super admin: <code>{config.admin_id}</code>"]
    if admins:
        lines.append("\n📋 Qo'shimcha adminlar:")
        for row in admins:
            lines.append(f"• <code>{row['user_id']}</code>")
    else:
        lines.append("\n📋 Qo'shimcha adminlar hozircha yo'q.")
    await message.answer("\n".join(lines))
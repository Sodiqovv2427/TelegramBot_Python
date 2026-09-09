"""
Ba'zi kanallarda "Approve new members" (join request) yoqilmagan bo'ladi — bunday holatda
ChatJoinRequest kelmaydi, foydalanuvchi to'g'ridan-to'g'ri a'zo bo'lib qoladi. Shu holatlarni ham
kuzatib, egasiga (yoki topilmasa ADMIN_ID'ga) xabar beramiz.

Eslatma: bu bildirishnoma FAQAT kanal egasiga (yoki ADMIN_ID'ga) yuboriladi — yangi qo'shilgan
foydalanuvchining o'ziga hech qanday xabar yuborilmaydi (TZ: silent-for-user talabi bilan izchil).
"""

import logging

import asyncpg
from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatMemberUpdated

import database as db
from config import config

logger = logging.getLogger("PlanningME_bot")
router = Router(name="member_updates")


@router.chat_member()
async def channel_member_updated(event: ChatMemberUpdated, db_pool: asyncpg.Pool):
    # Faqat "chiqib ketgan/olib tashlangan" -> "a'zo" o'tishini kuzatamiz (yangi qo'shilish)
    if event.old_chat_member.status not in ("left", "kicked"):
        return
    if event.new_chat_member.status != "member":
        return

    user = event.new_chat_member.user
    channel = await db.get_channel(db_pool, event.chat.id)

    # Avval DB'dagi kanal/guruh egasini, topilmasa ADMIN_ID'ni ishlatamiz
    target_admin = channel["owner_id"] if channel else None
    if not target_admin and config.admin_id:
        target_admin = config.admin_id

    if not target_admin:
        return

    try:
        await event.bot.send_message(
            chat_id=int(target_admin),
            text=(
                f"👤 <b>Yangi a'zo qo'shildi!</b>\n\n"
                f"<b>Ismi:</b> {user.full_name}\n"
                f"<b>Username:</b> @{user.username if user.username else 'yo‘q'}\n"
                f"<b>ID:</b> <code>{user.id}</code>\n"
                f"<b>Chat:</b> {event.chat.title}"
            ),
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.warning("Admin'ga notification yuborishda xatolik: %s", e)
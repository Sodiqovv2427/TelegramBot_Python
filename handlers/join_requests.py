"""
Module 2: Smart Auto-Approve Engine (SILENT)

TZ talabi: auto_approve yoqilgan bo'lsa, qo'shilish so'rovi TO'LIQ JIM tasdiqlanadi.
Bu yerda foydalanuvchiga (event.from_user.id) hech qachon send_message/send_photo va h.k.
chaqirilmasligi SHART — na welcome_message, na boshqa har qanday DM/PM. Faqat:
  1) approve_chat_join_request chaqiriladi;
  2) natija PostgreSQL'ga log qilinadi (join_requests jadvali).
Kanal egasiga xabar berish kerak bo'lsa, buning uchun alohida oqim (member_updates.py) mavjud.
"""

import logging

import asyncpg
from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatJoinRequest

import database as db

logger = logging.getLogger("PlanningME_bot")
router = Router(name="join_requests")


@router.chat_join_request()
async def handle_join_request(event: ChatJoinRequest, db_pool: asyncpg.Pool):
    channel = await db.get_channel(db_pool, event.chat.id)
    if not channel:
        # Bot ushbu kanalni tanimaydi (ro'yxatdan o'tmagan) — hech narsa qilmaymiz
        return

    if not channel["auto_approve"]:
        # Auto-approve o'chirilgan — so'rov tegilmasdan qoladi, admin Telegram'ning o'zida
        # (Requests to join) qo'lda ko'rib chiqadi.
        return

    # 1) JIM tasdiqlash — foydalanuvchiga HECH QANDAY DM/PM yuborilmaydi
    try:
        await event.bot.approve_chat_join_request(event.chat.id, event.from_user.id)
    except TelegramBadRequest as e:
        logger.warning("Join request tasdiqlab bo'lmadi: %s", e)
        return

    # 2) PostgreSQL'ga log
    invite_link = event.invite_link.invite_link if event.invite_link else None
    await db.log_join_request(db_pool, event.chat.id, event.from_user.id, invite_link)

    logger.info(
        "✅ %s (id=%s) '%s' kanaliga SILENT tasdiqlandi", event.from_user.full_name,
        event.from_user.id, channel["title"],
    )
    # Diqqat: bu yerdan keyin event.from_user.id'ga hech qanday xabar yuborilmaydi (TZ talabi).
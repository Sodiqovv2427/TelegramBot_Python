"""
Module 5: Bot administratorlarini boshqarish (Super-admin only)

Ommaviy xabar yuborish (broadcast) funksiyasi olib tashlandi — /newpost orqali kanal yoki
guruhga post rejalashtirish bilan bir xil vazifani bajarardi, shuning uchun ortiqcha edi.

Bu yerda faqat bot_admins jadvalini boshqarish buyruqlari qoladi (kelajakda admin-only
funksiyalar uchun kerak bo'lishi mumkin):
  /addadmin <user_id>    — bazaga admin qo'shadi
  /removeadmin <user_id> — bazadan adminni o'chiradi
  /admins                — joriy adminlar ro'yxati

Bularning barchasi FAQAT super admin (.env dagi ADMIN_ID) uchun ishlaydi.
"""

import logging

import asyncpg
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from config import config

logger = logging.getLogger("PlanningME_bot")
router = Router(name="broadcast")


def _is_super_admin(user_id: int) -> bool:
    return bool(config.admin_id) and user_id == config.admin_id


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
"""
Module 3: Execution Engine — pending postlarni davriy tekshirib, vaqti kelganlarini kanalga yuboradi.
"""

import logging

import asyncpg
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
from config import config
from keyboards import json_to_inline_keyboard

logger = logging.getLogger("PlanningME_bot")


async def publish_pending_posts(bot: Bot, db_pool: asyncpg.Pool):
    posts = await db.get_pending_posts(db_pool)
    for post in posts:
        markup = json_to_inline_keyboard(post["inline_keyboard"])
        try:
            if post["media_type"] == "photo":
                await bot.send_photo(
                    post["channel_id"], post["media_id"],
                    caption=post["content_text"], reply_markup=markup,
                )
            elif post["media_type"] == "video":
                await bot.send_video(
                    post["channel_id"], post["media_id"],
                    caption=post["content_text"], reply_markup=markup,
                )
            elif post["media_type"] == "document":
                await bot.send_document(
                    post["channel_id"], post["media_id"],
                    caption=post["content_text"], reply_markup=markup,
                )
            else:
                await bot.send_message(
                    post["channel_id"], post["content_text"] or "", reply_markup=markup,
                )

            await db.mark_post_published(db_pool, post["post_id"])
            logger.info("📤 Post #%s '%s' kanaliga yuborildi", post["post_id"], post["channel_id"])

        except (TelegramBadRequest, TelegramForbiddenError) as e:
            # Bot kanaldan chiqarib yuborilgan yoki xabar formatida xato bo'lishi mumkin.
            # Postni "published" deb belgilamaymiz — lekin cheksiz qayta urinishning oldini olish
            # uchun xatoni log qilib qo'yamiz. Kerak bo'lsa qo'lda qayta yuborish mumkin.
            logger.error("❌ Post #%s yuborilmadi: %s", post["post_id"], e)


def setup_scheduler(bot: Bot, db_pool: asyncpg.Pool) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        publish_pending_posts,
        trigger="interval",
        seconds=config.scheduler_interval_seconds,
        args=(bot, db_pool),
        id="publish_pending_posts",
        max_instances=1,
    )
    return scheduler
"""
All-In-One Telegram SMM & Channel Moderator Bot
Texnik stek: Python 3.13, aiogram 3.x, asyncpg (PostgreSQL), APScheduler

O'rnatish:
    pip install -r requirements.txt

.env fayl kerak (.env.example ga qarang).

Ishga tushirish:
    python main.py
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import config
from database import create_db_pool, init_db
from cache import build_fsm_storage, close_redis_client, get_redis_client
from middlewares import DbSessionMiddleware
from handlers import main_router
from scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("PlanningME_bot")


async def set_bot_commands(bot: Bot):
    """Telegram'ning chap-pastdagi Menu tugmasida ko'rinadigan buyruqlar ro'yxati."""
    commands = [
        BotCommand(command="start", description="Botni qayta ishga tushirish"),
        BotCommand(command="mychannels", description="Ulangan kanallarni boshqarish"),
        BotCommand(command="newpost", description="Yangi post rejalashtirish"),
    ]
    await bot.set_my_commands(commands)


async def main():
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # FSM holatlari endi Redis'da saqlanadi — bot qayta ishga tushganda (deploy/crash)
    # foydalanuvchining "post yaratish" kabi jarayondagi holati yo'qolmaydi.
    storage = build_fsm_storage()
    dp = Dispatcher(storage=storage)

    # Redis ulanishini oldindan tekshirib olamiz — muammo bo'lsa botni boshida to'xtatamiz,
    # keyinroq tasodifiy joyda tushunarsiz xato bermasin
    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        logger.info("✅ Redis ulanishi muvaffaqiyatli")
    except Exception as e:
        import sys
        sys.exit(f"❌ Redis'ga ulanib bo'lmadi: {e}")

    db_pool = await create_db_pool()
    await init_db(db_pool)

    # Global db_pool ni barcha handlerlarga uzatish (TZ 5-bo'lim talabi)
    dp.update.middleware(DbSessionMiddleware(db_pool))

    dp.include_router(main_router)

    await set_bot_commands(bot)

    scheduler = setup_scheduler(bot, db_pool)
    scheduler.start()

    print("\n-------------------------------------------")
    print("🤖 SMM & Channel Moderator bot ishga tushdi!")
    print("-------------------------------------------\n")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await db_pool.close()
        await close_redis_client()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Bot to'xtatildi.")
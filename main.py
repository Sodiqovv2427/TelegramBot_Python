"""
All-In-One Telegram SMM & Channel Moderator Bot
Texnik stek: Python 3.13, aiogram 3.x, asyncpg (PostgreSQL), APScheduler

O'rnatish:
    pip install -r requirements.txt

.env fayl kerak (.env.example ga qarang). Production'da (Render/Railway) DATABASE_URL
platform tomonidan avtomatik beriladi — alohida DB_USER/DB_PASSWORD/DB_NAME shart emas.

Ishga tushirish (lokal):
    python main.py

Ishga tushirish (Render/Railway worker):
    Procfile: worker: python main.py
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import config
from database import create_db_pool, init_db
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
        BotCommand(command="mychats", description="Kanallar va guruhlarni boshqarish"),
        BotCommand(command="newpost", description="Yangi post yaratish"),
    ]
    await bot.set_my_commands(commands)


async def main():
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    db_pool = await create_db_pool()
    await init_db(db_pool)

    # Global db_pool ni barcha handlerlarga uzatish (TZ 5-bo'lim talabi)
    dp.update.middleware(DbSessionMiddleware(db_pool))

    dp.include_router(main_router)

    await set_bot_commands(bot)

    scheduler = setup_scheduler(bot, db_pool)
    scheduler.start()

    logger.info("-------------------------------------------")
    logger.info("🤖 SMM & Channel Moderator bot ishga tushdi!")
    logger.info("-------------------------------------------")

    try:
        # chat_join_request va chat_member eventlarini olish uchun allowed_updates
        # aniq ko'rsatilishi shart (TZ 5-bo'lim talabi)
        await dp.start_polling(
            bot,
            allowed_updates=["message", "chat_member", "chat_join_request", "callback_query"],
        )
    finally:
        scheduler.shutdown(wait=False)
        await db_pool.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Bot to'xtatildi.")
"""
Barcha environment sozlamalarini shu yerdan o'qiymiz (TZ 5-bo'lim: "Strict Environment
Configuration"). Boshqa hech bir modul os.getenv() ni to'g'ridan-to'g'ri chaqirmasligi kerak —
hammasi shu fayldan import qilinadi.

PRODUCTION ESLATMA: Railway/Render kabi platformalarda odatda bitta DATABASE_URL environment
o'zgaruvchisi beriladi (masalan: postgres://user:pass@host:port/dbname). Shu sabab bu fayl
DATABASE_URL mavjud bo'lsa, DB_USER/DB_PASSWORD/DB_NAME kabi alohida o'zgaruvchilarni talab
qilmaydi — ular DATABASE_URL ichidan asyncpg tomonidan avtomatik o'qiladi.
"""

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    # Railway/Render: to'liq Postgres connection string (agar berilgan bo'lsa, ustuvor ishlatiladi)
    database_url: str | None
    db_user: str | None
    db_password: str | None
    db_host: str
    db_port: int
    db_name: str | None
    db_ssl: bool
    # Group Guard sozlamalari (.env orqali qo'shimcha taqiqlangan so'zlar)
    blacklisted_words: tuple[str, ...]
    # Scheduler necha soniyada bir marta pending postlarni tekshiradi
    scheduler_interval_seconds: int
    # Kanal egasi topilmasa (yoki DB'da yo'q bo'lsa), bildirishnoma shu ID'ga yuboriladi
    admin_id: int | None


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"❌ .env faylida '{name}' topilmadi. .env.example fayliga qarang.")
    return value


def load_config() -> Config:
    database_url = os.getenv("DATABASE_URL") or None

    db_port_raw = os.getenv("DB_PORT", "5432")
    try:
        db_port = int(db_port_raw)
    except ValueError:
        sys.exit("❌ DB_PORT butun son bo'lishi kerak (masalan: 5432)")

    blacklist_raw = os.getenv("BLACKLISTED_WORDS", "")
    blacklist = tuple(w.strip().lower() for w in blacklist_raw.split(",") if w.strip())

    admin_id_raw = os.getenv("ADMIN_ID")
    admin_id = None
    if admin_id_raw:
        try:
            admin_id = int(admin_id_raw)
        except ValueError:
            sys.exit("❌ ADMIN_ID butun son (Telegram user ID) bo'lishi kerak")

    if database_url:
        # DATABASE_URL berilgan bo'lsa (Railway/Render), alohida DB_USER/DB_PASSWORD/DB_NAME shart emas
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        db_name = os.getenv("DB_NAME")
    else:
        # Lokal / klassik muhitda hammasi alohida-alohida shart
        db_user = _require("DB_USER")
        db_password = _require("DB_PASSWORD")
        db_name = _require("DB_NAME")

    return Config(
        bot_token=_require("BOT_TOKEN"),
        database_url=database_url,
        db_user=db_user,
        db_password=db_password,
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=db_port,
        db_name=db_name,
        db_ssl=os.getenv("DB_SSL", "false").strip().lower() in ("1", "true", "yes"),
        blacklisted_words=blacklist,
        scheduler_interval_seconds=int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "30")),
        admin_id=admin_id,
    )


config = load_config()
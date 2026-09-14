"""
Barcha environment sozlamalarini shu yerdan o'qiymiz (TZ 5-bo'lim: "Strict Environment
Configuration"). Boshqa hech bir modul os.getenv() ni to'g'ridan-to'g'ri chaqirmasligi kerak —
hammasi shu fayldan import qilinadi.
"""

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    # Railway PostgreSQL plugin qo'shsangiz, u avtomatik DATABASE_URL beradi — shuni ustuvor ishlatamiz
    database_url: str | None
    db_user: str | None
    db_password: str | None
    db_host: str | None
    db_port: int
    db_name: str | None
    db_ssl: bool
    # Redis — FSM storage va cache uchun
    redis_url: str | None
    redis_host: str
    redis_port: int
    redis_password: str | None
    redis_db: int
    # Group Guard sozlamalari
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
    # Railway'da Postgres plugin qo'shilsa, u DATABASE_URL (yoki PG*) o'zgaruvchilarini
    # o'zi yaratadi. Shu bo'lsa — DB_USER/DB_PASSWORD/DB_HOST/DB_NAME talab qilinmaydi.
    database_url = os.getenv("DATABASE_URL")

    db_port_raw = os.getenv("DB_PORT", "5432")
    try:
        db_port = int(db_port_raw)
    except ValueError:
        sys.exit("❌ DB_PORT butun son bo'lishi kerak (masalan: 5432)")

    if database_url:
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        db_name = os.getenv("DB_NAME")
    else:
        db_user = _require("DB_USER")
        db_password = _require("DB_PASSWORD")
        db_name = _require("DB_NAME")

    db_ssl = os.getenv("DB_SSL", "false").lower() == "true"

    # Redis: agar REDIS_URL berilgan bo'lsa (masalan Railway/Upstash), o'shani ustuvor ishlatamiz.
    # Bo'lmasa REDIS_HOST/PORT/PASSWORD/DB dan yig'ib olamiz (lokal/docker-compose uchun qulay).
    redis_url = os.getenv("REDIS_URL")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port_raw = os.getenv("REDIS_PORT", "6379")
    try:
        redis_port = int(redis_port_raw)
    except ValueError:
        sys.exit("❌ REDIS_PORT butun son bo'lishi kerak (masalan: 6379)")
    redis_password = os.getenv("REDIS_PASSWORD") or None
    redis_db_raw = os.getenv("REDIS_DB", "0")
    try:
        redis_db = int(redis_db_raw)
    except ValueError:
        sys.exit("❌ REDIS_DB butun son bo'lishi kerak (masalan: 0)")

    blacklist_raw = os.getenv("BLACKLISTED_WORDS", "")
    blacklist = tuple(w.strip().lower() for w in blacklist_raw.split(",") if w.strip())

    admin_id_raw = os.getenv("ADMIN_ID")
    admin_id = None
    if admin_id_raw:
        try:
            admin_id = int(admin_id_raw)
        except ValueError:
            sys.exit("❌ ADMIN_ID butun son (Telegram user ID) bo'lishi kerak")

    return Config(
        bot_token=_require("BOT_TOKEN"),
        database_url=database_url,
        db_user=db_user,
        db_password=db_password,
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=db_port,
        db_name=db_name,
        db_ssl=db_ssl,
        redis_url=redis_url,
        redis_host=redis_host,
        redis_port=redis_port,
        redis_password=redis_password,
        redis_db=redis_db,
        blacklisted_words=blacklist,
        scheduler_interval_seconds=int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "30")),
        admin_id=admin_id,
    )


config = load_config()
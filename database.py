"""
Yagona global asyncpg.Pool va shu bazaga tegishli barcha SQL so'rovlar shu yerda.
TZ 5-bo'lim: "Use a single global asyncpg.Pool instance initialized in main() and
passed to handlers via middleware".

Handlerlar bevosita SQL yozmaydi — faqat shu fayldagi funksiyalarni chaqiradi.
Bu SQL xatolarini bitta joyda tuzatish imkonini beradi va handlerlarni soddaligicha saqlaydi.

PRODUCTION (Render/Railway): agar .env / platform environment'da DATABASE_URL mavjud bo'lsa,
pool aynan shu connection string orqali ochiladi (host/port/user/password alohida kerak emas).
Aks holda, config.py'dagi alohida DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME ishlatiladi
(lokal development uchun qulay).
"""

import json
import sys
from datetime import datetime
from typing import Any, Optional

import asyncpg

from config import config


# ============ POOL YARATISH ============

async def _init_connection(conn: asyncpg.Connection):
    """Har bir yangi ulanishda jsonb ustunlarini avtomatik JSON <-> dict qilib beradi."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def create_db_pool() -> asyncpg.Pool:
    ssl_mode = "require" if config.db_ssl else None
    try:
        if config.database_url:
            # Railway/Render: DATABASE_URL orqali to'g'ridan-to'g'ri ulanish
            pool = await asyncpg.create_pool(
                dsn=config.database_url,
                min_size=1,
                max_size=10,
                init=_init_connection,
                ssl=ssl_mode,
            )
        else:
            # Lokal development: alohida-alohida DB_* qiymatlar
            pool = await asyncpg.create_pool(
                user=config.db_user,
                password=config.db_password,
                host=config.db_host,
                port=config.db_port,
                database=config.db_name,
                min_size=1,
                max_size=10,
                init=_init_connection,
                ssl=ssl_mode,
            )
    except Exception as e:
        sys.exit(f"❌ PostgreSQL bazasiga ulanib bo'lmadi: {e}")
    return pool


async def init_db(pool: asyncpg.Pool):
    """Barcha jadvallarni FK tartibida yaratadi va eski bazalarni yangi ustunlar bilan migratsiya qiladi."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    full_name VARCHAR(255) NOT NULL,
                    username VARCHAR(255),
                    is_premium BOOLEAN DEFAULT FALSE,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id BIGINT PRIMARY KEY,
                    owner_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    title VARCHAR(255) NOT NULL,
                    chat_type VARCHAR(20) NOT NULL DEFAULT 'channel',
                    auto_approve BOOLEAN DEFAULT TRUE,
                    welcome_message TEXT,
                    welcome_media_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Eski (chat_type ustunisiz) bazalarni ham xavfsiz migratsiya qilamiz
            await conn.execute("""
                ALTER TABLE channels ADD COLUMN IF NOT EXISTS chat_type VARCHAR(20) NOT NULL DEFAULT 'channel';
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    post_id SERIAL PRIMARY KEY,
                    channel_id BIGINT REFERENCES channels(channel_id) ON DELETE CASCADE,
                    content_text TEXT,
                    media_id VARCHAR(255),
                    media_type VARCHAR(50),
                    inline_keyboard JSONB,
                    publish_at TIMESTAMP NOT NULL,
                    is_published BOOLEAN DEFAULT FALSE
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS join_requests (
                    request_id SERIAL PRIMARY KEY,
                    channel_id BIGINT REFERENCES channels(channel_id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    invite_link VARCHAR(255),
                    approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_admins (
                    user_id BIGINT PRIMARY KEY,
                    added_by BIGINT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
    print(
        "✅ PostgreSQL: barcha jadvallar tayyor "
        "(users, channels, scheduled_posts, join_requests, bot_admins)"
    )


# ============ USERS ============

async def upsert_user(pool: asyncpg.Pool, user_id: int, full_name: str, username: Optional[str]):
    await pool.execute(
        """
        INSERT INTO users (user_id, full_name, username)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE
        SET full_name = EXCLUDED.full_name, username = EXCLUDED.username;
        """,
        user_id, full_name, username,
    )


# ============ CHANNELS / GROUPS ============
# Eslatma: "channels" jadvali ham kanallarni, ham guruhlarni saqlaydi — ularni
# chat_type ustuni ('channel' | 'group') orqali ajratamiz.

async def upsert_channel(
    pool: asyncpg.Pool, channel_id: int, owner_id: int, title: str, chat_type: str = "channel"
):
    """Bot kanal/guruhga admin qilib qo'shilganda yoki title o'zgarganda chaqiriladi."""
    await pool.execute(
        """
        INSERT INTO channels (channel_id, owner_id, title, chat_type)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (channel_id) DO UPDATE
        SET title = EXCLUDED.title, chat_type = EXCLUDED.chat_type;
        """,
        channel_id, owner_id, title, chat_type,
    )


async def get_channel(pool: asyncpg.Pool, channel_id: int) -> Optional[asyncpg.Record]:
    return await pool.fetchrow("SELECT * FROM channels WHERE channel_id = $1;", channel_id)


async def get_user_channels(
    pool: asyncpg.Pool, owner_id: int, chat_type: Optional[str] = None
) -> list[asyncpg.Record]:
    """chat_type berilsa ('channel' yoki 'group'), faqat shu turdagilar qaytariladi."""
    if chat_type:
        return await pool.fetch(
            "SELECT * FROM channels WHERE owner_id = $1 AND chat_type = $2 ORDER BY created_at DESC;",
            owner_id, chat_type,
        )
    return await pool.fetch(
        "SELECT * FROM channels WHERE owner_id = $1 ORDER BY created_at DESC;", owner_id
    )


async def get_all_chats(pool: asyncpg.Pool, chat_type: Optional[str] = None) -> list[asyncpg.Record]:
    """Broadcast uchun: barcha ro'yxatdan o'tgan kanal/guruhlar (istalgan egadan)."""
    if chat_type:
        return await pool.fetch(
            "SELECT * FROM channels WHERE chat_type = $1 ORDER BY created_at DESC;", chat_type
        )
    return await pool.fetch("SELECT * FROM channels ORDER BY created_at DESC;")


async def toggle_auto_approve(pool: asyncpg.Pool, channel_id: int) -> bool:
    """auto_approve ni teskarisiga o'zgartiradi, yangi qiymatni qaytaradi."""
    row = await pool.fetchrow(
        """
        UPDATE channels SET auto_approve = NOT auto_approve
        WHERE channel_id = $1
        RETURNING auto_approve;
        """,
        channel_id,
    )
    return row["auto_approve"] if row else False


async def set_welcome_message(pool: asyncpg.Pool, channel_id: int, text: str):
    """
    Eslatma: welcome_message ustuni bazada saqlanadi (kelajakda kerak bo'lishi mumkin),
    lekin TZ talabiga ko'ra join-request oqimida foydalanuvchiga hech qachon DM
    sifatida yuborilmaydi (auto-approve butunlay SILENT). Shuning uchun bu funksiya
    hozirda hech bir handlerdan chaqirilmaydi.
    """
    await pool.execute(
        "UPDATE channels SET welcome_message = $1 WHERE channel_id = $2;", text, channel_id
    )


# ============ JOIN REQUESTS ============

async def log_join_request(
    pool: asyncpg.Pool, channel_id: int, user_id: int, invite_link: Optional[str]
):
    await pool.execute(
        """
        INSERT INTO join_requests (channel_id, user_id, invite_link)
        VALUES ($1, $2, $3);
        """,
        channel_id, user_id, invite_link,
    )


async def count_channel_joins(pool: asyncpg.Pool, channel_id: int) -> int:
    return await pool.fetchval(
        "SELECT COUNT(*) FROM join_requests WHERE channel_id = $1;", channel_id
    )


# ============ SCHEDULED POSTS ============

async def create_scheduled_post(
    pool: asyncpg.Pool,
    channel_id: int,
    content_text: Optional[str],
    media_id: Optional[str],
    media_type: Optional[str],
    inline_keyboard: Optional[list],
    publish_at: datetime,
) -> int:
    post_id = await pool.fetchval(
        """
        INSERT INTO scheduled_posts
            (channel_id, content_text, media_id, media_type, inline_keyboard, publish_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING post_id;
        """,
        channel_id, content_text, media_id, media_type, inline_keyboard, publish_at,
    )
    return post_id


async def get_pending_posts(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT * FROM scheduled_posts
        WHERE is_published = FALSE AND publish_at <= NOW()
        ORDER BY publish_at ASC;
        """
    )


async def mark_post_published(pool: asyncpg.Pool, post_id: int):
    await pool.execute(
        "UPDATE scheduled_posts SET is_published = TRUE WHERE post_id = $1;", post_id
    )


# ============ BOT ADMINS (Broadcast ruxsatlari) ============
# ADMIN_ID (.env) — "super admin", har doim ruxsati bor va shu jadvaldan mustaqil ishlaydi.
# bot_admins — super admin tomonidan /addadmin bilan qo'shilgan qo'shimcha adminlar.

async def add_bot_admin(pool: asyncpg.Pool, user_id: int, added_by: int):
    await pool.execute(
        """
        INSERT INTO bot_admins (user_id, added_by)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO NOTHING;
        """,
        user_id, added_by,
    )


async def remove_bot_admin(pool: asyncpg.Pool, user_id: int) -> bool:
    result = await pool.execute("DELETE FROM bot_admins WHERE user_id = $1;", user_id)
    # asyncpg "DELETE N" ko'rinishida qaytaradi
    return result.split()[-1] != "0"


async def list_bot_admins(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch("SELECT * FROM bot_admins ORDER BY added_at ASC;")


async def is_bot_admin(pool: asyncpg.Pool, user_id: int) -> bool:
    row = await pool.fetchrow("SELECT 1 FROM bot_admins WHERE user_id = $1;", user_id)
    return row is not None
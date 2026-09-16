"""
Redis integratsiyasi — ikkita mustaqil vazifa uchun:

1) FSM STORAGE — foydalanuvchi suhbat holatini (masalan post yaratish jarayonidagi qadam)
   xotirada emas, Redis'da saqlaydi. Bu bot qayta ishga tushganda (deploy, crash-restart)
   foydalanuvchi FSM holati YO'QOLMASLIGINI ta'minlaydi — hozirgi MemoryStorage esa
   har restart'da hamma holatni unutadi.

2) CACHE (Cache-Aside pattern) — tez-tez so'raladigan, kamdan-kam o'zgaradigan ma'lumotlarni
   (masalan foydalanuvchining kanallar ro'yxati) PostgreSQL'ga har safar so'rov yubormasdan,
   qisqa muddat Redis'da saqlab turish orqali baza yukini kamaytiradi.

Bu fayl ikkalasi uchun ham yagona kirish nuqtasi: boshqa modullar to'g'ridan-to'g'ri
`redis.asyncio`ni import qilmaydi, faqat shu yerdagi funksiyalarni chaqiradi.
"""

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis
from aiogram.fsm.storage.redis import RedisStorage

from config import config

logger = logging.getLogger("PlanningME_bot")

# Cache kalitlari uchun umumiy prefiks — boshqa loyihalar bilan bitta Redis'ni
# baham ko'rsangiz, kalitlar bir-biriga aralashib ketmasligi uchun.
CACHE_PREFIX = "smmbot:cache:"

# Standart TTL (soniyalarda) — bu vaqtdan keyin kesh o'zi eskiradi va bazadan qayta o'qiladi.
DEFAULT_TTL = 300  # 5 daqiqa


def _build_redis_url() -> str:
    """
    REDIS_URL berilgan bo'lsa o'shani, bo'lmasa HOST/PORT/PASSWORD/DB'dan yig'ib qaytaradi.
    aiogram'ning RedisStorage.from_url() va redis.asyncio.from_url() ikkalasi ham shu formatni kutadi.
    """
    if config.redis_url:
        return config.redis_url
    auth = f":{config.redis_password}@" if config.redis_password else ""
    return f"redis://{auth}{config.redis_host}:{config.redis_port}/{config.redis_db}"


# ============ ULANISH ============

_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> redis.Redis:
    """Butun ilova uchun bitta umumiy (singleton) Redis ulanish pool'i."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            _build_redis_url(),
            decode_responses=True,   # qiymatlarni avtomatik str (bytes emas) qilib qaytaradi
            max_connections=20,
        )
    return _redis_client


async def close_redis_client():
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


def build_fsm_storage() -> RedisStorage:
    """
    main.py'da Dispatcher(storage=...) ga shu qaytadi.
    MemoryStorage o'rniga — bot qayta ishga tushganda foydalanuvchi FSM holati saqlanib qoladi.
    """
    return RedisStorage.from_url(_build_redis_url())


# ============ CACHE-ASIDE YORDAMCHI FUNKSIYALARI ============

async def cache_get(key: str) -> Optional[Any]:
    """Kalit bo'yicha keshdan o'qiydi. JSON sifatida saqlangan qiymatni avtomatik dekod qiladi."""
    client = await get_redis_client()
    try:
        raw = await client.get(CACHE_PREFIX + key)
    except Exception as e:
        # Redis vaqtincha ishlamay qolsa ham bot ishlashda davom etishi kerak — faqat log yozamiz
        logger.warning("Redis GET xato (key=%s): %s", key, e)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL):
    """Qiymatni JSON qilib keshga yozadi, TTL (soniya) bilan."""
    client = await get_redis_client()
    try:
        await client.set(CACHE_PREFIX + key, json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        logger.warning("Redis SET xato (key=%s): %s", key, e)


async def cache_delete(key: str):
    """Kalitni keshdan o'chiradi — ma'lumot yangilanganda (invalidation) chaqiriladi."""
    client = await get_redis_client()
    try:
        await client.delete(CACHE_PREFIX + key)
    except Exception as e:
        logger.warning("Redis DELETE xato (key=%s): %s", key, e)


async def cache_delete_prefix(prefix: str):
    """Berilgan prefiks bilan boshlanadigan barcha kalitlarni o'chiradi (masalan bitta user uchun)."""
    client = await get_redis_client()
    try:
        pattern = f"{CACHE_PREFIX}{prefix}*"
        async for key in client.scan_iter(match=pattern, count=100):
            await client.delete(key)
    except Exception as e:
        logger.warning("Redis DELETE (prefix=%s) xato: %s", prefix, e)
"""
TZ 5-bo'lim: "...passed to handlers via middleware or state context."
Bu middleware har bir kelgan update uchun db_pool ni handler argumentlariga qo'shib beradi,
shunda har bir handler funksiyasi shunchaki `db_pool: asyncpg.Pool` parametrini qabul qiladi.
"""

from typing import Any, Awaitable, Callable, Dict

import asyncpg
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["db_pool"] = self.pool
        return await handler(event, data)
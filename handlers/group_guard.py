"""
Module 4: Group Guard & Anti-Spam (ENHANCED)

Bog'langan guruhlarda quyidagilarni avtomatik o'chiradi (adminlar bundan mustasno):
  - Har qanday havola: http(s)://..., www...., t.me/..., telegram.me/...
  - @username ko'rinishidagi eslatmalar (mentions)
  - Reklama/spam so'zlar ro'yxati (standart + .env BLACKLISTED_WORDS orqali kengaytiriladi)

Aniqlash ikki bosqichda ishlaydi:
  1) Xabar matni/izohi ustida regex (tez, oddiy holatlar uchun)
  2) Telegram entity'lari (url, text_link, mention, text_mention) — bu formatlangan
     havola/mention'larni ham (masalan matnga "bu yerga" deb yashiringan link) ushlaydi.
"""

import logging
import re

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message

from config import config

logger = logging.getLogger("PlanningME_bot")
router = Router(name="group_guard")

ADMIN_STATUSES = {"administrator", "creator"}

# Standart reklama/spam so'zlar (TZ talabi bo'yicha)
SPAM_KEYWORDS: tuple[str, ...] = (
    "kuniga pullik",
    "reklama",
    "crypto",
    "kassa",
    "daromad",
    "moliya",
)

LINK_RE = re.compile(r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+)", re.IGNORECASE)
MENTION_RE = re.compile(r"@\w{3,}")

LINK_ENTITY_TYPES = {"url", "text_link"}
MENTION_ENTITY_TYPES = {"mention", "text_mention"}


async def _is_admin(message: Message) -> bool:
    # Anonim admin sifatida yozilgan xabar (kanal nomidan) — admin deb hisoblanadi
    if message.sender_chat is not None:
        return True
    if message.from_user is None:
        return False
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ADMIN_STATUSES
    except (TelegramBadRequest, TelegramForbiddenError):
        return False


def _has_link_or_mention_entities(message: Message) -> bool:
    entities = list(message.entities or []) + list(message.caption_entities or [])
    for entity in entities:
        if entity.type in LINK_ENTITY_TYPES or entity.type in MENTION_ENTITY_TYPES:
            return True
    return False


def _violates_rules(message: Message) -> bool:
    text = message.text or message.caption or ""

    # 1) Entity-based (formatlangan / yashiringan havola va mentionlar)
    if _has_link_or_mention_entities(message):
        return True

    if not text:
        return False

    # 2) Regex-based (oddiy matnli havola/mention)
    if LINK_RE.search(text) or MENTION_RE.search(text):
        return True

    # 3) Spam kalit so'zlar (standart + .env BLACKLISTED_WORDS)
    lowered = text.lower()
    if any(word in lowered for word in SPAM_KEYWORDS):
        return True
    if any(word in lowered for word in config.blacklisted_words):
        return True

    return False


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text | F.caption)
async def group_guard(message: Message):
    if not _violates_rules(message):
        return
    if await _is_admin(message):
        return

    try:
        await message.delete()
        logger.info(
            "🛡 Spam xabar o'chirildi: chat=%s user=%s", message.chat.id,
            message.from_user.id if message.from_user else "noma'lum",
        )
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        # Botda o'chirish huquqi yo'q bo'lishi mumkin
        logger.warning("Xabarni o'chirib bo'lmadi: %s", e)


# ============ 🛡 Guruh Guard (Sozlamalar) — joriy qoidalarni ko'rsatish ============

@router.message(F.text == "🛡 Guruh Guard (Sozlamalar)")
async def show_group_guard_settings(message: Message):
    extra_words = ", ".join(config.blacklisted_words) if config.blacklisted_words else "— (qo'shilmagan)"
    text = (
        "🛡 <b>Guruh Guard — joriy sozlamalar</b>\n\n"
        "Ulangan guruhlarda quyidagi xabarlar avtomatik o'chiriladi "
        "(guruh adminlari va egalari bundan mustasno):\n\n"
        "🔗 Har qanday havola (http/https, www., t.me/, telegram.me/)\n"
        "👤 @username ko'rinishidagi eslatmalar (mentions)\n"
        f"🚫 Standart spam so'zlar: <i>{', '.join(SPAM_KEYWORDS)}</i>\n"
        f"⚙️ Qo'shimcha taqiqlangan so'zlar (.env): <i>{extra_words}</i>\n\n"
        "Bu sozlamalar hozircha global (barcha guruhlar uchun bir xil) va faqat "
        "server administratori tomonidan .env fayl orqali o'zgartiriladi."
    )
    await message.answer(text)
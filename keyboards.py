from typing import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ============ CALLBACK DATA SXEMALARI ============

class ChannelCB(CallbackData, prefix="ch"):
    action: str          # "open" | "toggle" | "edit_welcome" | "back"
    channel_id: int


class NewPostChannelCB(CallbackData, prefix="np"):
    channel_id: int


class PostConfirmCB(CallbackData, prefix="pc"):
    action: str  # "confirm" | "cancel"


class BroadcastConfirmCB(CallbackData, prefix="bc"):
    action: str  # "confirm" | "cancel"


# Reply-keyboard tugma matnlari — broadcast.py shu aynan matnlar bilan taqqoslaydi (F.text == ...)
CHANNEL_BROADCAST_BTN = "📣 Kanalga e'lon yuborish"
GROUP_BROADCAST_BTN = "💬 Guruhga e'lon yuborish"


# ============ Pastki (persistent) reply-keyboard ============

def main_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📢 Mening kanallarim"), KeyboardButton(text="✍️ Yangi post")],
        [KeyboardButton(text="📊 Analitika"), KeyboardButton(text="⚙️ Sozlamalar")],
        [KeyboardButton(text="👥 Referal"), KeyboardButton(text="ℹ️ Yordam")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text=CHANNEL_BROADCAST_BTN), KeyboardButton(text=GROUP_BROADCAST_BTN)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, is_persistent=True)


# ============ /start menyusi ============

def start_menu_kb(bot_username: str) -> InlineKeyboardMarkup:
    """
    /start javobiga qo'shiladigan inline klaviatura:
    - Kanal/guruhga to'g'ridan-to'g'ri qo'shish tugmalari (startchannel/startgroup deep-link)
    - Tezkor amallar: Mening kanallarim / Yangi post
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Kanalga qo'shish",
                    url=f"https://t.me/{bot_username}?startchannel=true",
                ),
                InlineKeyboardButton(
                    text="💬 Guruhga qo'shish",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                ),
            ],
            [
                InlineKeyboardButton(text="📋 Mening kanallarim", callback_data="btn_mychannels"),
                InlineKeyboardButton(text="✍️ Yangi post", callback_data="btn_newpost"),
            ],
        ]
    )


# ============ /mychannels ============

def channels_list_kb(channels: Iterable) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(
            text=f"📢 {ch['title']}",
            callback_data=ChannelCB(action="open", channel_id=ch["channel_id"]),
        )
    builder.adjust(1)
    return builder.as_markup()


def channel_dashboard_kb(channel) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status = "🟢 Auto-approve: ON" if channel["auto_approve"] else "🔴 Auto-approve: OFF"
    builder.button(
        text=status,
        callback_data=ChannelCB(action="toggle", channel_id=channel["channel_id"]),
    )
    builder.button(
        text="✏️ Welcome xabarni tahrirlash",
        callback_data=ChannelCB(action="edit_welcome", channel_id=channel["channel_id"]),
    )
    builder.button(text="⬅️ Orqaga", callback_data=ChannelCB(action="back", channel_id=0))
    builder.adjust(1)
    return builder.as_markup()


# ============ /newpost ============

def channels_choice_kb(channels: Iterable) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(
            text=f"📢 {ch['title']}",
            callback_data=NewPostChannelCB(channel_id=ch["channel_id"]),
        )
    builder.adjust(1)
    return builder.as_markup()


def post_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash va rejalashtirish", callback_data=PostConfirmCB(action="confirm"))
    builder.button(text="❌ Bekor qilish", callback_data=PostConfirmCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def build_post_inline_keyboard(raw_lines: list[str]) -> InlineKeyboardMarkup | None:
    """
    "Button Text - https://example.com" formatidagi qatorlardan InlineKeyboardMarkup yasaydi.
    Har bir qator = alohida qator (row) tugma. Format noto'g'ri bo'lgan qatorlar tashlab ketiladi.
    """
    builder = InlineKeyboardBuilder()
    added = False
    for line in raw_lines:
        if " - " not in line:
            continue
        text, url = line.rsplit(" - ", 1)
        text, url = text.strip(), url.strip()
        if not text or not url.startswith(("http://", "https://")):
            continue
        builder.button(text=text, url=url)
        added = True
    if not added:
        return None
    builder.adjust(1)
    return builder.as_markup()


def inline_keyboard_to_json(markup: InlineKeyboardMarkup | None) -> list | None:
    """DB'ga JSONB sifatida saqlash uchun oddiy list[list[dict]] ko'rinishiga o'giradi."""
    if markup is None:
        return None
    return [
        [{"text": btn.text, "url": btn.url} for btn in row]
        for row in markup.inline_keyboard
    ]


def json_to_inline_keyboard(data: list | None) -> InlineKeyboardMarkup | None:
    """DB'dan o'qilgan JSON strukturani qayta InlineKeyboardMarkup'ga aylantiradi."""
    if not data:
        return None
    builder = InlineKeyboardBuilder()
    for row in data:
        for btn in row:
            builder.button(text=btn["text"], url=btn["url"])
    builder.adjust(1)
    return builder.as_markup()


# ============ Broadcast tasdiqlash ============

def broadcast_confirm_kb(count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Ha, {count} taga yuborish", callback_data=BroadcastConfirmCB(action="confirm"))
    builder.button(text="❌ Bekor qilish", callback_data=BroadcastConfirmCB(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()
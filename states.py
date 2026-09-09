from aiogram.fsm.state import State, StatesGroup


class PostCreation(StatesGroup):
    choosing_channel = State()
    waiting_content = State()
    waiting_buttons = State()
    waiting_time = State()
    confirm = State()


class BroadcastStates(StatesGroup):
    """
    📣 Kanalga e'lon yuborish / 💬 Guruhga e'lon yuborish oqimi uchun.
    Faqat super admin (ADMIN_ID) yoki bazadagi bot_admins ro'yxatidagi foydalanuvchilar
    bu holatlarga kira oladi (handlers/broadcast.py'dagi ruxsat tekshiruvi orqali).
    """
    waiting_content = State()   # admin xabar (matn/rasm/video/fayl) yuboradi
    confirm = State()           # yuborishdan oldin "Ha/Yo'q" tasdiqlash
from aiogram.fsm.state import State, StatesGroup


class PostCreation(StatesGroup):
    choosing_type = State()
    choosing_channel = State()
    waiting_content = State()
    waiting_buttons = State()
    waiting_time = State()
    confirm = State()


class WelcomeSetup(StatesGroup):
    waiting_text = State()


class BroadcastStates(StatesGroup):
    waiting_content = State()
    confirm = State()
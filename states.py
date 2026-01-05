from aiogram.fsm.state import State, StatesGroup


class DonateStates(StatesGroup):
    awaiting_currency = State()
    awaiting_amount = State()
    awaiting_proof = State()


class AdminSetCardStates(StatesGroup):
    awaiting_currency = State()
    awaiting_card = State()
    awaiting_confirm = State()


class AdminSupportMessageStates(StatesGroup):
    awaiting_message = State()
    awaiting_confirm = State()

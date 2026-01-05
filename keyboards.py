from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)

import database as db
from i18n import LANG_BUTTON_TEXTS, TRANSLATIONS


def get_main_menu(lang: str, is_admin: bool = False):
    """Inline main menu keyboard."""
    rows = [
        [
            InlineKeyboardButton(text=TRANSLATIONS[lang]["MENU_DONATE"], callback_data="menu_donate"),
            InlineKeyboardButton(text=TRANSLATIONS[lang]["MENU_HISTORY"], callback_data="menu_history"),
        ],
        [
            InlineKeyboardButton(text=TRANSLATIONS[lang]["MENU_PROFILE"], callback_data="menu_profile"),
            InlineKeyboardButton(text=TRANSLATIONS[lang]["MENU_SUPPORT"], callback_data="menu_support"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text=TRANSLATIONS[lang]["ADMIN_PANEL"], callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_cancel_keyboard(lang: str):
    """Inline cancel button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=TRANSLATIONS[lang]["CANCEL"], callback_data="cancel")]]
    )


def get_language_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=LANG_BUTTON_TEXTS["ru"], callback_data="lang_ru")],
            [InlineKeyboardButton(text=LANG_BUTTON_TEXTS["uk"], callback_data="lang_uk")],
            [InlineKeyboardButton(text=LANG_BUTTON_TEXTS["en"], callback_data="lang_en")],
        ]
    )


async def get_currency_keyboard(enabled: list[str] | None = None):
    """Async currency keyboard - fetches currencies with active cards."""
    enabled_currencies = enabled if enabled is not None else await db.get_enabled_donation_currencies()
    # Only show currencies that have active cards
    currencies_with_cards = set(await db.get_currencies_with_active_cards())
    available_currencies = [c for c in enabled_currencies if c in currencies_with_cards]
    rows = []
    for code in available_currencies:
        if code == "UAH":
            text = "🇺🇦 UAH"
        elif code == "RUB":
            text = "🇷🇺 RUB"
        elif code == "USD":
            text = "🇺🇸 USD"
        else:
            continue
        rows.append([InlineKeyboardButton(text=text, callback_data=f"currency_{code}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_admin_currency_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇺🇦 UAH", callback_data="admin_currency_UAH")],
            [InlineKeyboardButton(text="🇷🇺 RUB", callback_data="admin_currency_RUB")],
            [InlineKeyboardButton(text="🇺🇸 USD", callback_data="admin_currency_USD")],
        ]
    )


# For removing reply keyboard when switching to inline
REMOVE_KEYBOARD = ReplyKeyboardRemove()

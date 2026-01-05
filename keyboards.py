from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import database as db
from i18n import LANG_BUTTON_TEXTS, TRANSLATIONS


def get_main_menu(lang: str, is_admin: bool = False):
    rows = [
        [
            KeyboardButton(text=TRANSLATIONS[lang]["MENU_DONATE"]),
            KeyboardButton(text=TRANSLATIONS[lang]["MENU_HISTORY"]),
        ],
        [
            KeyboardButton(text=TRANSLATIONS[lang]["MENU_PROFILE"]),
            KeyboardButton(text=TRANSLATIONS[lang]["MENU_SUPPORT"]),
        ],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=TRANSLATIONS[lang]["ADMIN_PANEL"])])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_cancel_keyboard(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TRANSLATIONS[lang]["CANCEL"])]],
        resize_keyboard=True,
    )


def get_language_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=LANG_BUTTON_TEXTS["ru"], callback_data="lang_ru")],
            [InlineKeyboardButton(text=LANG_BUTTON_TEXTS["uk"], callback_data="lang_uk")],
            [InlineKeyboardButton(text=LANG_BUTTON_TEXTS["en"], callback_data="lang_en")],
        ]
    )


def get_currency_keyboard(enabled: list[str] | None = None):
    enabled_currencies = enabled if enabled is not None else db.get_enabled_donation_currencies()
    rows = []
    for code in enabled_currencies:
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

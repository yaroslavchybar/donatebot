import logging
import html

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext

import database as db
from config import ADMIN_ID
from i18n import (
    LANGS,
    TRANSLATIONS,
    fetch_user_lang,
    get_user_lang,
    set_cached_user_lang,
    t_for,
)
from keyboards import get_cancel_keyboard, get_currency_keyboard, get_language_keyboard, get_main_menu
from states import DonateStates

logger = logging.getLogger(__name__)

router = Router(name="user")


async def safe_edit_text(message: Message, text: str, **kwargs) -> bool:
    """Safely edit message text, handling 'message is not modified' gracefully.
    
    Returns True if edit was successful or message was unchanged.
    Returns False if edit failed for other reasons (caller should send new message).
    """
    try:
        await message.edit_text(text, **kwargs)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return True  # Content is the same, no action needed
        return False  # Other error, caller should handle
    except Exception:
        return False


def _is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID


def _parse_referrer_id(args: str, prefix: str, self_user_id: int) -> int | None:
    if not args.startswith(prefix):
        return None
    raw = args.removeprefix(prefix)
    try:
        referrer_id = int(raw)
    except ValueError:
        return None
    if referrer_id == self_user_id:
        return None
    return referrer_id


def _parse_donate_args(args: str, self_user_id: int) -> tuple[float, int | None] | None:
    if not args.startswith("donate_"):
        return None
    parts = args.split("_")
    if len(parts) < 2:
        return None

    try:
        amount = float(parts[1])
    except ValueError:
        return None
    if amount <= 0:
        return None

    referrer_id: int | None = None
    if len(parts) > 2:
        try:
            parsed_referrer = int(parts[2])
            if parsed_referrer != self_user_id:
                referrer_id = parsed_referrer
        except ValueError:
            referrer_id = None

    return amount, referrer_id


def _parse_profile_referrer(args: str, self_user_id: int) -> int | None:
    prefixed = _parse_referrer_id(args, "profile_", self_user_id)
    if prefixed is not None:
        return prefixed
    if args.isdigit():
        try:
            referrer_id = int(args)
        except ValueError:
            return None
        if referrer_id == self_user_id:
            return None
        return referrer_id
    return None


async def _start_donation(
    message: Message, state: FSMContext, user_id: int, amount: float, referrer_id: int | None, currency: str, *, edit: bool = False
) -> None:
    if referrer_id is None:
        text = t_for(user_id, "REFERRAL_REQUIRED")
        if edit:
            try:
                await message.edit_text(text)
            except Exception:
                await message.answer(text)
        else:
            await message.answer(text)
        return

    # Check for active card BEFORE creating transaction
    card_info = await db.get_next_active_card(currency)
    if not card_info:
        await state.clear()
        text = t_for(user_id, "NO_CARD_FOR_CURRENCY", currency=currency)
        keyboard = get_main_menu(get_user_lang(user_id), is_admin=_is_admin(user_id))
        if edit:
            try:
                await message.edit_text(text, reply_markup=keyboard)
            except Exception:
                await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)
        return

    transaction_id = await db.create_transaction(user_id, amount, referrer_id, currency)
    if not transaction_id:
        text = t_for(user_id, "TRANSACTION_FAILED")
        if edit:
            try:
                await message.edit_text(text)
            except Exception:
                await message.answer(text)
        else:
            await message.answer(text)
        return

    await state.update_data(
        current_transaction_id=transaction_id,
        donation_amount=amount,
        currency=currency,
        card_info=card_info,
        recipient_id=referrer_id,
    )

    lang = get_user_lang(user_id)

    currency_symbols = {"USD": "$", "UAH": "₴", "RUB": "₽"}
    symbol = currency_symbols.get(currency, currency)
    
    referrer_text = t_for(user_id, "REFERRED_BY_LABEL") if referrer_id else ""
    formatted_amount = f"{symbol} {amount:,.2f}"
    
    text = (
        t_for(user_id, "DONATION_INIT_HEADER", amount=formatted_amount, referrer_text=referrer_text) + "\n\n" +
        f"{t_for(user_id,'TRANSFER_HEADER',amount=formatted_amount)}\n\n"
        f"<code>{card_info}</code>\n\n"
        f"{t_for(user_id,'TAP_TO_COPY')}\n"
        f"<b>{t_for(user_id,'UPLOAD_RECEIPT')}</b>"
    )
    keyboard = get_cancel_keyboard(lang)
    
    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    
    await state.set_state(DonateStates.awaiting_proof)


async def _send_main_menu(message: Message, user_id: int, first_name: str, *, edit: bool = False) -> None:
    lang = get_user_lang(user_id)
    text = t_for(user_id, "WELCOME", first_name=first_name)
    keyboard = get_main_menu(lang, is_admin=_is_admin(user_id))
    
    if edit:
        try:
            await message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


async def _send_profile(message: Message, bot: Bot, user_id: int, full_name: str, username: str | None, referrer_id: int | None, *, edit: bool = False) -> None:
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    if referrer_id and referrer_id != user_id:
        ref = await db.get_user(referrer_id)
        ref_username = ref[1] if ref else None
        ref_first_name = ref[2] if ref else "Member"
        lang = get_user_lang(user_id)
        text = (
            f"{TRANSLATIONS[lang]['MEMBER_PROFILE_TITLE']}\n\n"
            f"{TRANSLATIONS[lang]['PROFILE_NAME']}: {ref_first_name}\n"
            f"{TRANSLATIONS[lang]['PROFILE_USERNAME']}: @{ref_username or 'N/A'}\n\n"
            f"{TRANSLATIONS[lang]['SUPPORT_MEMBER_DONATE']}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=TRANSLATIONS[lang]["DONATE_BUTTON"],
                        callback_data=f"donate_to_{referrer_id}",
                    )
                ],
                [InlineKeyboardButton(text="⬅️ " + TRANSLATIONS[lang].get("BACK", "Back"), callback_data="back_menu")]
            ]
        )
        if edit:
            try:
                await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
            except Exception:
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        return

    total_donated = await db.get_user_total_donated(user_id)
    lang = get_user_lang(user_id)
    text = (
        f"{TRANSLATIONS[lang]['PROFILE_TITLE']}\n\n"
        f"{TRANSLATIONS[lang]['PROFILE_NAME']}: {full_name}\n"
        f"{TRANSLATIONS[lang]['PROFILE_USERNAME']}: @{username or 'N/A'}\n"
        f"{TRANSLATIONS[lang]['PROFILE_TOTAL_DONATED']}: 💰 {total_donated:,.2f}\n\n"
        f"{TRANSLATIONS[lang]['YOUR_PROFILE_LINK_TITLE']}\n"
        f"<code>https://t.me/{bot_username}?start={user_id}</code>\n\n"
        f"{TRANSLATIONS[lang]['SHARE_PROFILE_LINK']}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ " + TRANSLATIONS[lang].get("BACK", "Back"), callback_data="back_menu")]
        ]
    )
    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(CommandStart())
async def start_handler(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    user = message.from_user
    await db.add_user(user.id, user.username, user.first_name)
    
    # Clean up any legacy reply keyboards
    try:
        msg = await message.answer("...", reply_markup=ReplyKeyboardRemove())
        await msg.delete()
    except Exception:
        pass
    
    # Fetch user language - returns None if new user
    user_lang = await fetch_user_lang(user.id)
    is_new_user = user_lang == "en" and await db.get_user_language(user.id) is None

    args = command.args or ""
    
    # If new user, ask for language first (save args for after language selection)
    if is_new_user:
        await state.update_data(start_args=args)
        await message.answer(
            TRANSLATIONS["en"]["SELECT_LANGUAGE_PROMPT"], reply_markup=get_language_keyboard()
        )
        return

    # Existing user - proceed directly with the flow
    if args.startswith("donate_"):
        parsed = _parse_donate_args(args, user.id)
        if parsed:
            amount, referrer_id = parsed
            await db.set_user_preferred_referrer(user.id, referrer_id)
            await state.update_data(donation_amount=amount, referrer_id=referrer_id)
            enabled = await db.get_enabled_donation_currencies()
            currencies_with_cards = set(await db.get_currencies_with_active_cards())
            available = [c for c in enabled if c in currencies_with_cards]
            if not available:
                await state.clear()
                await message.answer(
                    t_for(user.id, "NO_CURRENCIES_ENABLED"),
                    reply_markup=get_main_menu(get_user_lang(user.id), is_admin=_is_admin(user.id)),
                )
                return
            await message.answer(t_for(user.id, "SELECT_CURRENCY"), reply_markup=await get_currency_keyboard(enabled))
            await state.set_state(DonateStates.awaiting_currency)
            return

    referrer_id = _parse_profile_referrer(args, user.id)
    if referrer_id is not None or args.startswith("profile_") or args.isdigit():
        await db.set_user_preferred_referrer(user.id, referrer_id)
        await state.update_data(referrer_id=referrer_id)
        await _send_profile(message, bot, user.id, user.full_name, user.username, referrer_id)
        return

    await _send_main_menu(message, user.id, user.first_name)


# ===== MAIN MENU CALLBACKS =====

@router.callback_query(F.data == "menu_history")
async def history_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    history = await db.get_user_history(user_id)
    lang = get_user_lang(user_id)

    if not history:
        text = t_for(user_id, "HISTORY_EMPTY")
    else:
        text = t_for(user_id, "HISTORY_TITLE") + "\n\n"
        for tx in history:
            status_emoji = {
                "pending_proof": TRANSLATIONS[lang]["STATUS_PENDING_PROOF"],
                "pending_approval": TRANSLATIONS[lang]["STATUS_PENDING_APPROVAL"],
                "approved": TRANSLATIONS[lang]["STATUS_APPROVED"],
                "rejected": TRANSLATIONS[lang]["STATUS_REJECTED"],
            }.get(tx[2], tx[2])
            text += f"🆔 #{tx[0]} | 💰 {tx[1]} | {status_emoji}\n📅 {tx[3]}\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ " + TRANSLATIONS[lang].get("BACK", "Back"), callback_data="back_menu")]]
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu_profile")
async def profile_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user = callback.from_user
    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    await _send_profile(callback.message, bot, user.id, user.full_name, user.username, referrer_id, edit=True)
    await callback.answer()


@router.callback_query(F.data == "menu_support")
async def support_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    custom = await db.get_support_message()
    text = custom or t_for(user_id, "SUPPORT_MESSAGE")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ " + TRANSLATIONS[lang].get("BACK", "Back"), callback_data="back_menu")]]
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu_donate")
async def donate_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    if not referrer_id:
        referrer_id = await db.get_user_preferred_referrer(user_id)
    
    lang = get_user_lang(user_id)
    
    if referrer_id:
        ref = await db.get_user(referrer_id)
        ref_first_name = ref[2] if ref else "Member"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=TRANSLATIONS[lang]["DONATE_TO_MEMBER_NAME"].format(name=ref_first_name),
                        callback_data=f"donate_to_{referrer_id}",
                    )
                ],
                [InlineKeyboardButton(text="⬅️ " + TRANSLATIONS[lang].get("BACK", "Back"), callback_data="back_menu")]
            ]
        )
        text = TRANSLATIONS[lang]["ASK_RECIPIENT"]
        if not await safe_edit_text(callback.message, text, reply_markup=keyboard):
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    text = t_for(user_id, "REFERRAL_REQUIRED")
    keyboard = get_main_menu(lang, is_admin=_is_admin(user_id))
    if not await safe_edit_text(callback.message, text, reply_markup=keyboard):
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "back_menu")
async def back_menu_callback(callback: CallbackQuery):
    user = callback.from_user
    await _send_main_menu(callback.message, user.id, user.first_name, edit=True)
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    tx_id = data.get("current_transaction_id")
    if tx_id:
        try:
            await db.delete_transaction(int(tx_id))
        except Exception:
            pass
    await state.clear()
    
    lang = get_user_lang(user_id)
    text = t_for(user_id, "DONATION_CANCELLED")
    keyboard = get_main_menu(lang, is_admin=_is_admin(user_id))
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


# ===== DONATION FLOW CALLBACKS =====

@router.callback_query(F.data.startswith("donate_to_"))
async def donate_to_referrer_callback(callback: CallbackQuery, state: FSMContext):
    payload = callback.data
    try:
        ref_id = int(payload.split("_")[2])
    except Exception:
        await callback.answer()
        return
    if ref_id == callback.from_user.id:
        ref_id = None
    if ref_id is None:
        text = t_for(callback.from_user.id, "REFERRAL_REQUIRED")
        try:
            await callback.message.edit_text(text)
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
        return
    await state.update_data(referrer_id=ref_id)
    await db.set_user_preferred_referrer(callback.from_user.id, ref_id)
    enabled = await db.get_enabled_donation_currencies()
    currencies_with_cards = set(await db.get_currencies_with_active_cards())
    available = [c for c in enabled if c in currencies_with_cards]
    if not available:
        await state.clear()
        text = t_for(callback.from_user.id, "NO_CURRENCIES_ENABLED")
        keyboard = get_main_menu(get_user_lang(callback.from_user.id), is_admin=_is_admin(callback.from_user.id))
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        return
    text = t_for(callback.from_user.id, "SELECT_CURRENCY")
    keyboard = await get_currency_keyboard(enabled)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)
    await state.set_state(DonateStates.awaiting_currency)
    await callback.answer()


@router.callback_query(F.data.startswith("currency_"))
async def currency_selected_callback(callback: CallbackQuery, state: FSMContext):
    currency = callback.data.split("_")[1]
    enabled = await db.get_enabled_donation_currencies()
    enabled_set = set(enabled)
    if currency not in enabled_set:
        if not enabled:
            await state.clear()
            text = t_for(callback.from_user.id, "NO_CURRENCIES_ENABLED")
            keyboard = get_main_menu(get_user_lang(callback.from_user.id), is_admin=_is_admin(callback.from_user.id))
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except Exception:
                await callback.message.answer(text, reply_markup=keyboard)
            await callback.answer(t_for(callback.from_user.id, "ALERT_CURRENCY_DISABLED"), show_alert=True)
            return
        try:
            await callback.message.edit_reply_markup(reply_markup=await get_currency_keyboard(enabled))
        except Exception:
            pass
        await callback.answer(t_for(callback.from_user.id, "ALERT_CURRENCY_DISABLED"), show_alert=True)
        return
    await state.update_data(currency=currency)
    
    data = await state.get_data()
    amount = data.get("donation_amount")
    
    if amount:
        # Amount was already set via deep link
        user_id = callback.from_user.id
        referrer_id = data.get("referrer_id")
        await _start_donation(callback.message, state, user_id, amount, referrer_id, currency, edit=True)
    else:
        # Need to ask for amount
        text = t_for(callback.from_user.id, "ASK_AMOUNT")
        keyboard = get_cancel_keyboard(get_user_lang(callback.from_user.id))
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await state.set_state(DonateStates.awaiting_amount)
    
    await callback.answer()


@router.callback_query(F.data.in_(("lang_en", "lang_ru", "lang_uk")))
async def language_selected_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data_str = callback.data
    lang = data_str.split("_")[1]
    user_id = callback.from_user.id
    if lang not in LANGS:
        await callback.answer()
        return
    await db.set_user_language(user_id, lang)
    set_cached_user_lang(user_id, lang)  # Update cache
    stored = await state.get_data()
    args = stored.get("start_args")
    await state.update_data(start_args=None)
    
    if args and args.startswith("donate_"):
        try:
            parts = args.split("_")
            amount = float(parts[1])
            referrer_id = None
            if len(parts) > 2:
                try:
                    referrer_id = int(parts[2])
                    if referrer_id == user_id:
                        referrer_id = None
                except ValueError:
                    referrer_id = None
            await db.set_user_preferred_referrer(user_id, referrer_id)
            if referrer_id is None:
                text = t_for(user_id, "REFERRAL_REQUIRED")
                try:
                    await callback.message.edit_text(text)
                except Exception:
                    await callback.message.answer(text)
            else:
                await state.update_data(donation_amount=amount, referrer_id=referrer_id)
                enabled = await db.get_enabled_donation_currencies()
                currencies_with_cards = set(await db.get_currencies_with_active_cards())
                available = [c for c in enabled if c in currencies_with_cards]
                if not available:
                    await state.clear()
                    text = t_for(user_id, "NO_CURRENCIES_ENABLED")
                    keyboard = get_main_menu(get_user_lang(user_id), is_admin=_is_admin(user_id))
                    try:
                        await callback.message.edit_text(text, reply_markup=keyboard)
                    except Exception:
                        await callback.message.answer(text, reply_markup=keyboard)
                    await callback.answer("OK")
                    return
                text = t_for(user_id, "SELECT_CURRENCY")
                keyboard = await get_currency_keyboard(enabled)
                try:
                    await callback.message.edit_text(text, reply_markup=keyboard)
                except Exception:
                    await callback.message.answer(text, reply_markup=keyboard)
                await state.set_state(DonateStates.awaiting_currency)
        except Exception:
            await _send_main_menu(callback.message, user_id, callback.from_user.first_name, edit=True)
    elif args:
        referrer_id = _parse_profile_referrer(args, user_id)
        await db.set_user_preferred_referrer(user_id, referrer_id)
        await state.update_data(referrer_id=referrer_id)
        await _send_profile(callback.message, bot, user_id, callback.from_user.full_name, callback.from_user.username, referrer_id, edit=True)
    else:
        await _send_main_menu(callback.message, user_id, callback.from_user.first_name, edit=True)
    await callback.answer("OK")


@router.callback_query(F.data.in_(("genlink_custom", "genlink_profile")))
async def generate_link_callback(callback: CallbackQuery, bot: Bot):
    action = callback.data.split("_")[1]
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    if action == "custom":
        await callback.message.answer(
            "To generate a custom link, use this format:\n"
            f"<code>https://t.me/{bot_username}?start=donate_AMOUNT_{callback.from_user.id}</code>\n\n"
            "Replace AMOUNT with your number (e.g., 25.50).",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    if action == "profile":
        link = f"https://t.me/{bot_username}?start={callback.from_user.id}"
        await callback.message.answer(
            "🔗 <b>Your Profile Link</b>\n\n"
            f"<code>{link}</code>\n\n"
            "Share this to open your profile in the bot.\n"
            "Donations started after opening via this link will credit you as referrer.",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    amount = action
    link = f"https://t.me/{bot_username}?start=donate_{amount}_{callback.from_user.id}"

    await callback.message.answer(
        f"🔗 <b>Donation Link for ${amount}</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Share this link! When clicked, it will start a donation for this amount,\n"
        "and you will be credited as the referrer.",
        parse_mode="HTML",
    )
    await callback.answer()


# ===== MESSAGE HANDLERS FOR STATES =====

@router.message(DonateStates.awaiting_amount, F.text)
async def receive_amount_handler(message: Message, state: FSMContext):
    text = message.text
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        await message.answer(t_for(message.from_user.id, "INVALID_AMOUNT"))
        return

    user_id = message.from_user.id

    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    currency = data.get("currency", "USD")
    await _start_donation(message, state, user_id, amount, referrer_id, currency)


@router.message(DonateStates.awaiting_proof, F.photo)
async def receive_proof_handler(message: Message, state: FSMContext, bot: Bot):
    if not message.photo:
        await message.answer(t_for(message.from_user.id, "UPLOAD_RECEIPT_PROMPT"))
        return

    photo = message.photo[-1]
    file_id = photo.file_id

    data = await state.get_data()
    transaction_id = data.get("current_transaction_id")
    amount = data.get("donation_amount")
    user = message.from_user

    if not transaction_id:
        await message.answer(
            t_for(message.from_user.id, "SESSION_EXPIRED"),
            reply_markup=get_main_menu(
                get_user_lang(message.from_user.id),
                is_admin=_is_admin(message.from_user.id),
            ),
        )
        await state.clear()
        return

    await db.update_transaction_proof(transaction_id, file_id)

    try:
            tx_details = await db.get_transaction(transaction_id)
            if not tx_details:
                await message.answer(t_for(message.from_user.id, "TRANSACTION_NOT_FOUND"))
                await state.clear()
                return

            tx_amount = tx_details[2]
            tx_currency = tx_details[3]
            recipient_id = tx_details[7] if len(tx_details) > 7 else None
            if recipient_id is None:
                recipient_id = data.get("recipient_id") or data.get("referrer_id")
            if recipient_id is None:
                await message.answer(t_for(message.from_user.id, "TRANSACTION_NOT_FOUND"))
                await state.clear()
                return
            recipient_id = int(recipient_id)

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t_for(recipient_id, "BTN_APPROVE"), callback_data=f"approve_{transaction_id}"
                        ),
                        InlineKeyboardButton(
                            text=t_for(recipient_id, "BTN_REJECT"), callback_data=f"reject_{transaction_id}"
                        ),
                    ]
                ]
            )

            currency_symbols = {"USD": "$", "UAH": "₴", "RUB": "₽"}
            symbol = currency_symbols.get(tx_currency, tx_currency)
            formatted_amount = f"{symbol} {float(tx_amount):,.2f}"

            if user.username:
                sender = f"@{user.username} (ID: {user.id})"
            else:
                sender = f"ID: {user.id}"
            sender = html.escape(sender)

            receiver = "N/A"
            recipient = await db.get_user(recipient_id)
            recipient_username = recipient[1] if recipient else None
            if recipient_username:
                receiver = f"@{recipient_username} (ID: {recipient_id})"
            else:
                receiver = f"ID: {recipient_id}"
            receiver = html.escape(receiver)

            raw_card_info = data.get("card_info")
            if raw_card_info:
                card = f"<code>{html.escape(str(raw_card_info))}</code>"
            else:
                card = "N/A"

            await bot.send_photo(
                chat_id=recipient_id,
                photo=file_id,
                caption=t_for(recipient_id, "ADMIN_NEW_CLAIM_TITLE") + "\n\n" +
                t_for(
                    recipient_id,
                    "ADMIN_CLAIM_DETAILS",
                    sender=sender,
                    amount=formatted_amount,
                    card=card,
                    tx_id=transaction_id,
                    receiver=receiver,
                ),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception as e:
        logger.error(f"Failed to send for confirmation: {e}")

    await message.answer(
        t_for(message.from_user.id, "RECEIPT_RECEIVED"),
        reply_markup=get_main_menu(
            get_user_lang(message.from_user.id),
            is_admin=_is_admin(message.from_user.id),
        ),
    )

    await state.clear()


def register_user_handlers(dp: Dispatcher):
    dp.include_router(router)

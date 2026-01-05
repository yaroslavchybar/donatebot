import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.fsm.context import FSMContext

import database as db
from config import ADMIN_ID
from i18n import (
    ADMIN_PANEL_TEXTS,
    CANCEL_TEXTS,
    DONATE_TEXTS,
    HISTORY_TEXTS,
    LANGS,
    PROFILE_TEXTS,
    SUPPORT_TEXTS,
    TRANSLATIONS,
    get_user_lang,
    t_for,
)
from keyboards import get_cancel_keyboard, get_currency_keyboard, get_language_keyboard, get_main_menu
from states import DonateStates

logger = logging.getLogger(__name__)

router = Router(name="user")

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
    message: Message, state: FSMContext, user_id: int, amount: float, referrer_id: int | None, currency: str
) -> None:
    if referrer_id is None:
        await message.answer(t_for(user_id, "REFERRAL_REQUIRED"))
        return
    transaction_id = db.create_transaction(user_id, amount, referrer_id, currency)
    if not transaction_id:
        await message.answer(t_for(user_id, "TRANSACTION_FAILED"))
        return

    await state.update_data(current_transaction_id=transaction_id, donation_amount=amount, currency=currency)

    card_info = db.get_next_active_card(currency)
    if not card_info:
        card_block = t_for(user_id, "NO_CARD_FOR_CURRENCY", currency=currency)
    else:
        card_block = card_info
    lang = get_user_lang(user_id)

    currency_symbols = {"USD": "$", "UAH": "₴", "RUB": "₽"}
    symbol = currency_symbols.get(currency, currency)
    
    referrer_text = t_for(user_id, "REFERRED_BY_LABEL") if referrer_id else ""
    formatted_amount = f"{symbol} {amount:,.2f}"
    
    await message.answer(
        t_for(user_id, "DONATION_INIT_HEADER", amount=formatted_amount, referrer_text=referrer_text) + "\n\n" +
        f"{t_for(user_id,'TRANSFER_HEADER',amount=formatted_amount)}\n\n"
        f"<code>{card_block}</code>\n\n"
        f"{t_for(user_id,'TAP_TO_COPY')}\n"
        f"<b>{t_for(user_id,'UPLOAD_RECEIPT')}</b>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(lang),
    )
    await state.set_state(DonateStates.awaiting_proof)


async def _send_own_menu(message: Message) -> None:
    user = message.from_user
    lang = get_user_lang(user.id)
    await message.answer(
        t_for(user.id, "WELCOME", first_name=user.first_name),
        reply_markup=get_main_menu(lang, is_admin=_is_admin(user.id)),
    )


async def _send_profile(message: Message, bot: Bot, referrer_id: int | None) -> None:
    user = message.from_user
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    if referrer_id and referrer_id != user.id:
        ref = db.get_user(referrer_id)
        ref_username = ref[1] if ref else None
        ref_first_name = ref[2] if ref else "Member"
        lang = get_user_lang(user.id)
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
                ]
            ]
        )
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        return

    total_donated = db.get_user_total_donated(user.id)
    lang = get_user_lang(user.id)
    text = (
        f"{TRANSLATIONS[lang]['PROFILE_TITLE']}\n\n"
        f"{TRANSLATIONS[lang]['PROFILE_NAME']}: {user.full_name}\n"
        f"{TRANSLATIONS[lang]['PROFILE_USERNAME']}: @{user.username or 'N/A'}\n"
        f"{TRANSLATIONS[lang]['PROFILE_TOTAL_DONATED']}: 💰 {total_donated:,.2f}\n\n"
        f"{TRANSLATIONS[lang]['YOUR_PROFILE_LINK_TITLE']}\n"
        f"<code>https://t.me/{bot_username}?start={user.id}</code>\n\n"
        f"{TRANSLATIONS[lang]['SHARE_PROFILE_LINK']}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(CommandStart())
async def start_handler(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    user = message.from_user
    db.add_user(user.id, user.username, user.first_name)

    args = command.args or ""
    existing_lang = db.get_user_language(user.id)
    # Determine if the start deep-link includes a referrer; if so, skip language prompt
    has_referrer = False
    donate_parsed = _parse_donate_args(args, user.id)
    if donate_parsed:
        _, donate_referrer = donate_parsed
        has_referrer = donate_referrer is not None
    else:
        profile_referrer = _parse_profile_referrer(args, user.id)
        has_referrer = profile_referrer is not None
    if not has_referrer:
        await state.update_data(start_args=args)
        await message.answer(
            TRANSLATIONS["en"]["SELECT_LANGUAGE_PROMPT"], reply_markup=get_language_keyboard()
        )
        return

    if args.startswith("donate_"):
        parsed = _parse_donate_args(args, user.id)
        if parsed:
            amount, referrer_id = parsed
            db.set_user_preferred_referrer(user.id, referrer_id)
            # Ask for currency instead of starting immediately
            await state.update_data(donation_amount=amount, referrer_id=referrer_id)
            enabled = db.get_enabled_donation_currencies()
            if not enabled:
                await state.clear()
                await message.answer(
                    t_for(user.id, "NO_CURRENCIES_ENABLED"),
                    reply_markup=get_main_menu(get_user_lang(user.id), is_admin=_is_admin(user.id)),
                )
                return
            await message.answer(t_for(user.id, "SELECT_CURRENCY"), reply_markup=get_currency_keyboard(enabled))
            await state.set_state(DonateStates.awaiting_currency)
            return

    referrer_id = _parse_profile_referrer(args, user.id)
    if referrer_id is not None or args.startswith("profile_") or args.isdigit():
        db.set_user_preferred_referrer(user.id, referrer_id)
        await state.update_data(referrer_id=referrer_id)
        await _send_profile(message, bot, referrer_id)
        return

    await _send_own_menu(message)


@router.message(F.text.in_(HISTORY_TEXTS))
async def my_history_handler(message: Message):
    user_id = message.from_user.id
    history = db.get_user_history(user_id)

    if not history:
        await message.answer(t_for(user_id, "HISTORY_EMPTY"))
        return

    text = t_for(user_id, "HISTORY_TITLE") + "\n\n"
    for tx in history:
        lang = get_user_lang(user_id)
        status_emoji = {
            "pending_proof": TRANSLATIONS[lang]["STATUS_PENDING_PROOF"],
            "pending_approval": TRANSLATIONS[lang]["STATUS_PENDING_APPROVAL"],
            "approved": TRANSLATIONS[lang]["STATUS_APPROVED"],
            "rejected": TRANSLATIONS[lang]["STATUS_REJECTED"],
        }.get(tx[2], tx[2])

        text += f"🆔 #{tx[0]} | 💰 {tx[1]} | {status_emoji}\n📅 {tx[3]}\n\n"

    await message.answer(text, parse_mode="HTML")


@router.message(F.text.in_(PROFILE_TEXTS))
async def profile_handler(message: Message, bot: Bot, referrer_id: int | None = None):
    await _send_profile(message, bot, referrer_id)


@router.callback_query(F.data.in_(("genlink_custom", "genlink_profile")))
async def generate_link_callback(callback: CallbackQuery, bot: Bot):
    action = callback.data.split("_")[1]
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    if action == "custom":
        await callback.message.answer(
            "To generate a custom link, use this format:\n"
            f"<code>https://t.me/{bot_username}?start=donate_AMOUNT_{callback.from_user.id}</code>\n\n"
            "Replace AMOUNT with your number (e.g., 25.50)."
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
        await callback.message.answer(t_for(callback.from_user.id, "REFERRAL_REQUIRED"))
        await callback.answer()
        return
    await state.update_data(referrer_id=ref_id)
    db.set_user_preferred_referrer(callback.from_user.id, ref_id)
    enabled = db.get_enabled_donation_currencies()
    if not enabled:
        await state.clear()
        await callback.message.answer(
            t_for(callback.from_user.id, "NO_CURRENCIES_ENABLED"),
            reply_markup=get_main_menu(get_user_lang(callback.from_user.id), is_admin=_is_admin(callback.from_user.id)),
        )
        await callback.answer()
        return
    await callback.message.answer(
        t_for(callback.from_user.id, "SELECT_CURRENCY"),
        reply_markup=get_currency_keyboard(enabled),
    )
    await state.set_state(DonateStates.awaiting_currency)
    await callback.answer()


@router.callback_query(F.data.startswith("currency_"))
async def currency_selected_callback(callback: CallbackQuery, state: FSMContext):
    currency = callback.data.split("_")[1]
    enabled = db.get_enabled_donation_currencies()
    enabled_set = set(enabled)
    if currency not in enabled_set:
        if not enabled:
            await state.clear()
            await callback.message.answer(
                t_for(callback.from_user.id, "NO_CURRENCIES_ENABLED"),
                reply_markup=get_main_menu(get_user_lang(callback.from_user.id), is_admin=_is_admin(callback.from_user.id)),
            )
            await callback.answer(t_for(callback.from_user.id, "ALERT_CURRENCY_DISABLED"), show_alert=True)
            return
        try:
            await callback.message.edit_reply_markup(reply_markup=get_currency_keyboard(enabled))
        except Exception:
            await callback.message.answer(
                t_for(callback.from_user.id, "SELECT_CURRENCY"),
                reply_markup=get_currency_keyboard(enabled),
            )
        await callback.answer(t_for(callback.from_user.id, "ALERT_CURRENCY_DISABLED"), show_alert=True)
        return
    await state.update_data(currency=currency)
    
    data = await state.get_data()
    amount = data.get("donation_amount")
    
    if amount:
        # Amount was already set via deep link
        user_id = callback.from_user.id
        referrer_id = data.get("referrer_id")
        await _start_donation(callback.message, state, user_id, amount, referrer_id, currency)
    else:
        # Need to ask for amount
        await callback.message.answer(
            t_for(callback.from_user.id, "ASK_AMOUNT"),
            reply_markup=get_cancel_keyboard(get_user_lang(callback.from_user.id)),
        )
        await state.set_state(DonateStates.awaiting_amount)
    
    await callback.answer()


@router.callback_query(F.data.in_(("lang_en", "lang_ru", "lang_uk")))
async def language_selected_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = callback.data
    lang = data.split("_")[1]
    user_id = callback.from_user.id
    if lang not in LANGS:
        await callback.answer()
        return
    db.set_user_language(user_id, lang)
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
            db.set_user_preferred_referrer(user_id, referrer_id)
            if referrer_id is None:
                await callback.message.answer(t_for(user_id, "REFERRAL_REQUIRED"))
            else:
                await state.update_data(donation_amount=amount, referrer_id=referrer_id)
                enabled = db.get_enabled_donation_currencies()
                if not enabled:
                    await state.clear()
                    await callback.message.answer(
                        t_for(user_id, "NO_CURRENCIES_ENABLED"),
                        reply_markup=get_main_menu(get_user_lang(user_id), is_admin=_is_admin(user_id)),
                    )
                    await callback.answer("OK")
                    return
                await callback.message.answer(
                    t_for(user_id, "SELECT_CURRENCY"),
                    reply_markup=get_currency_keyboard(enabled)
                )
                await state.set_state(DonateStates.awaiting_currency)
        except Exception:
            await callback.message.answer(
                t_for(user_id, "WELCOME", first_name=callback.from_user.first_name),
                reply_markup=get_main_menu(lang, is_admin=(user_id == ADMIN_ID)),
            )
    elif args:
        referrer_id = _parse_profile_referrer(args, user_id)
        db.set_user_preferred_referrer(user_id, referrer_id)
        await state.update_data(referrer_id=referrer_id)
        await profile_handler(callback.message, bot, referrer_id=referrer_id)
    else:
        await callback.message.answer(
            t_for(user_id, "WELCOME", first_name=callback.from_user.first_name),
            reply_markup=get_main_menu(lang, is_admin=(user_id == ADMIN_ID)),
        )
    await callback.answer("OK")


@router.message(F.text.in_(SUPPORT_TEXTS))
async def support_handler(message: Message):
    custom = db.get_support_message()
    await message.answer(custom or t_for(message.from_user.id, "SUPPORT_MESSAGE"))


@router.message(F.text.in_(DONATE_TEXTS))
async def start_donate_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    if not referrer_id:
        referrer_id = db.get_user_preferred_referrer(message.from_user.id)
    if referrer_id:
        ref = db.get_user(referrer_id)
        ref_first_name = ref[2] if ref else "Member"
        lang = get_user_lang(message.from_user.id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=TRANSLATIONS[lang]["DONATE_TO_MEMBER_NAME"].format(name=ref_first_name),
                        callback_data=f"donate_to_{referrer_id}",
                    )
                ],
            ]
        )
        await message.answer(TRANSLATIONS[lang]["ASK_RECIPIENT"], reply_markup=keyboard)
        return
    await message.answer(t_for(message.from_user.id, "REFERRAL_REQUIRED"))


@router.message(F.text.in_(CANCEL_TEXTS))
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    data = await state.get_data()
    tx_id = data.get("current_transaction_id")
    if tx_id:
        try:
            db.delete_transaction(int(tx_id))
        except Exception:
            pass
    await state.clear()
    await message.answer(
        t_for(message.from_user.id, "DONATION_CANCELLED"),
        reply_markup=get_main_menu(
            get_user_lang(message.from_user.id),
            is_admin=(message.from_user.id == ADMIN_ID),
        ),
    )


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
    currency = data.get("currency", "USD") # Default to USD if something goes wrong, but state should have it
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
                is_admin=(message.from_user.id == ADMIN_ID),
            ),
        )
        await state.clear()
        return

    db.update_transaction_proof(transaction_id, file_id)

    if ADMIN_ID:
        try:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t_for(ADMIN_ID, "BTN_APPROVE"), callback_data=f"approve_{transaction_id}"
                        ),
                        InlineKeyboardButton(
                            text=t_for(ADMIN_ID, "BTN_REJECT"), callback_data=f"reject_{transaction_id}"
                        ),
                    ]
                ]
            )

            tx_details = db.get_transaction(transaction_id)
            if not tx_details:
                await message.answer(t_for(message.from_user.id, "TRANSACTION_NOT_FOUND"))
                await state.clear()
                return

            referrer_info = ""
            if len(tx_details) > 6 and tx_details[6]:
                referrer_id = tx_details[6]
                referrer_info = t_for(ADMIN_ID, "REFERRED_BY_ID", referrer_id=referrer_id)

            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=file_id,
                caption=t_for(ADMIN_ID, "ADMIN_NEW_CLAIM_TITLE") + "\n\n" +
                t_for(ADMIN_ID, "ADMIN_CLAIM_DETAILS", username=user.username, donor_id=user.id, amount=amount, tx_id=transaction_id, referrer_info=referrer_info),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Failed to send to admin: {e}")

    await message.answer(
        t_for(message.from_user.id, "RECEIPT_RECEIVED"),
        reply_markup=get_main_menu(
            get_user_lang(message.from_user.id),
            is_admin=(message.from_user.id == ADMIN_ID),
        ),
    )

    await state.clear()


def register_user_handlers(dp: Dispatcher):
    dp.include_router(router)

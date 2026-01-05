import logging
import re

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
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
from i18n import t_for
from keyboards import get_admin_currency_keyboard
from states import AdminSetCardStates, AdminSupportMessageStates

logger = logging.getLogger(__name__)

router = Router(name="admin")

def _is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID


def _get_admin_panel_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t_for(user_id, "BTN_VIEW_STATS"), callback_data="admin_stats")],
            [InlineKeyboardButton(text=t_for(user_id, "BTN_ADD_CARD"), callback_data="admin_setcard")],
            [InlineKeyboardButton(text=t_for(user_id, "BTN_MANAGE_CARDS"), callback_data="admin_cards")],
            [InlineKeyboardButton(text=t_for(user_id, "BTN_MANAGE_CURRENCIES"), callback_data="admin_currencies")],
            [InlineKeyboardButton(text=t_for(user_id, "BTN_MANAGE_SUPPORT"), callback_data="admin_support")],
            [InlineKeyboardButton(text="⬅️ " + t_for(user_id, "BACK"), callback_data="back_menu")],
        ]
    )

def _card_number_label(details: str) -> str | None:
    digits = "".join(ch for ch in details if ch.isdigit())
    if len(digits) >= 12:
        groups = [digits[i : i + 4] for i in range(0, len(digits), 4)]
        return " ".join(groups)
    return None

async def _send_manage_cards(message: Message, user_id: int, *, replace: bool = False):
    cards = await db.list_cards()
    if not cards:
        text = t_for(user_id, "ADMIN_NO_CARDS")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t_for(user_id, "BTN_ADD_CARD"), callback_data="admin_setcard")]]
        )
        if replace:
            try:
                await message.edit_text(text, reply_markup=keyboard)
                return
            except Exception:
                pass
        await message.answer(text, reply_markup=keyboard)
        return
    rows = []
    for cid, details, is_active, created_at, currency in cards:
        status = t_for(user_id, "STATUS_ACTIVE") if is_active == 1 else t_for(user_id, "STATUS_INACTIVE")
        label = _card_number_label(details) or (details if len(details) <= 90 else details[:90] + "...")
        label = f"[{currency}] {label}"
        rows.append([InlineKeyboardButton(text=f"{label} • {status}", callback_data="noop")])
        rows.append(
            [
                InlineKeyboardButton(
                    text=(t_for(user_id, "BTN_DEACTIVATE") if is_active == 1 else t_for(user_id, "BTN_ACTIVATE")),
                    callback_data=f"card_toggle_{cid}",
                ),
                InlineKeyboardButton(text=t_for(user_id, "BTN_DELETE"), callback_data=f"card_delete_{cid}"),
            ]
        )
    rows.append([InlineKeyboardButton(text=t_for(user_id, "BTN_ADD_CARD"), callback_data="admin_setcard")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="back_admin")])
    text = t_for(user_id, "MANAGE_CARDS_TITLE")
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if replace:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

async def _send_manage_currencies(message: Message, user_id: int, *, replace: bool = False):
    enabled = set(await db.get_enabled_donation_currencies())
    rows = []
    for code in db.SUPPORTED_CURRENCIES:
        is_on = code in enabled
        status = t_for(user_id, "CURRENCY_ENABLED_LABEL") if is_on else t_for(user_id, "CURRENCY_DISABLED_LABEL")
        mark = "✅" if is_on else "❌"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {code} • {status}",
                    callback_data=f"admin_toggle_currency_{code}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="back_admin")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    text = t_for(user_id, "MANAGE_CURRENCIES_TITLE")
    if replace:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "menu_admin")
async def admin_panel_callback_from_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return
    text = t_for(user_id, "ADMIN_PANEL_TITLE")
    keyboard = _get_admin_panel_keyboard(user_id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "back_admin")
async def back_admin_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return
    text = t_for(user_id, "ADMIN_PANEL_TITLE")
    keyboard = _get_admin_panel_keyboard(user_id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.in_(("admin_stats", "admin_setcard", "admin_cards", "admin_currencies", "admin_support")))
async def admin_panel_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return
    action = callback.data
    if action == "admin_stats":
        data = await db.get_stats()
        text = t_for(user_id, "STATS_TITLE") + "\n\n" + t_for(user_id, "STATS_DETAILS", **data)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ " + t_for(user_id, "BACK"), callback_data="back_admin")]]
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    elif action == "admin_setcard":
        text = t_for(user_id, "PROMPT_ADD_CARD")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ " + t_for(user_id, "BACK"), callback_data="back_admin")]]
        )
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await state.set_state(AdminSetCardStates.awaiting_card)
    elif action == "admin_cards":
        await _send_manage_cards(callback.message, user_id, replace=True)
    elif action == "admin_currencies":
        await _send_manage_currencies(callback.message, user_id, replace=True)
    elif action == "admin_support":
        current = await db.get_support_message() or t_for(user_id, "NO_SUPPORT_MESSAGE")
        text = t_for(user_id, "PROMPT_UPDATE_SUPPORT", current=current)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ " + t_for(user_id, "BACK"), callback_data="back_admin")]]
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await state.set_state(AdminSupportMessageStates.awaiting_message)
    await callback.answer()

@router.callback_query(F.data.startswith("admin_toggle_currency_"))
async def admin_toggle_currency_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer()
        return
    currency = parts[3]
    current = set(await db.get_enabled_donation_currencies())
    new_enabled = currency not in current
    await db.set_donation_currency_enabled(currency, new_enabled)
    await callback.answer(t_for(user_id, "ALERT_UPDATED"))
    await _send_manage_currencies(callback.message, user_id, replace=True)


@router.message(Command("setcard"))
async def set_card_handler(message: Message, command: CommandObject, state: FSMContext):
    user_id = message.from_user.id
    if not _is_admin(user_id):
        logger.warning(f"Unauthorized access attempt by {user_id}. Expected Admin: {ADMIN_ID}")
        await message.answer(t_for(user_id, "NOT_AUTHORIZED"))
        return

    args = command.args
    if not args:
        await message.answer(t_for(user_id, "PROMPT_CARD_DETAILS"))
        await state.set_state(AdminSetCardStates.awaiting_card)
        return

    await db.add_card(args, active=True)
    await _send_manage_cards(message, user_id)


@router.message(AdminSetCardStates.awaiting_card)
async def admin_receive_card_details(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not _is_admin(user_id):
        await message.answer(t_for(user_id, "NOT_AUTHORIZED"))
        return
    details = message.text.strip()
    await state.update_data(pending_card_details=details)
    await message.answer(t_for(user_id, "SELECT_CURRENCY"), reply_markup=get_admin_currency_keyboard())
    await state.set_state(AdminSetCardStates.awaiting_currency)

@router.callback_query(F.data.startswith("admin_currency_"))
async def admin_currency_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return

    currency = callback.data.split("_")[2]
    await state.update_data(pending_card_currency=currency)
    data = await state.get_data()
    details = data.get("pending_card_details")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t_for(user_id, "BTN_CONFIRM"), callback_data="confirm_setcard"),
                InlineKeyboardButton(text=t_for(user_id, "BTN_CANCEL_X"), callback_data="cancel_setcard"),
            ]
        ]
    )
    text = t_for(user_id, "REVIEW_CARD_DETAILS", details=f"[{currency}] {details}")
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(AdminSetCardStates.awaiting_confirm)
    await callback.answer()

@router.message(AdminSupportMessageStates.awaiting_message)
async def admin_receive_support_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not _is_admin(user_id):
        await message.answer(t_for(user_id, "NOT_AUTHORIZED"))
        return
    text = message.text.strip()
    await state.update_data(pending_support_message=text)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t_for(user_id, "BTN_CONFIRM"), callback_data="confirm_support"),
                InlineKeyboardButton(text=t_for(user_id, "BTN_CANCEL_X"), callback_data="cancel_support"),
            ]
        ]
    )
    await message.answer(
        t_for(user_id, "REVIEW_SUPPORT_MESSAGE", text=text),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await state.set_state(AdminSupportMessageStates.awaiting_confirm)


@router.callback_query(F.data.in_(("confirm_setcard", "cancel_setcard")))
async def admin_setcard_confirm_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return
    action = callback.data
    if action == "confirm_setcard":
        data = await state.get_data()
        details = data.get("pending_card_details")
        currency = data.get("pending_card_currency", "USD")
        if details:
            await db.add_card(details, active=True, currency=currency)
        await state.clear()
        await _send_manage_cards(callback.message, user_id, replace=True)
        await callback.answer(t_for(user_id, "ALERT_UPDATED"))
    elif action == "cancel_setcard":
        await state.clear()
        text = t_for(user_id, "ADMIN_PANEL_TITLE")
        keyboard = _get_admin_panel_keyboard(user_id)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer(t_for(user_id, "ALERT_CANCELLED"))

@router.callback_query(F.data.in_(("confirm_support", "cancel_support")))
async def admin_support_confirm_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return
    action = callback.data
    if action == "confirm_support":
        data = await state.get_data()
        msg_text = data.get("pending_support_message")
        if msg_text:
            await db.set_support_message(msg_text)
        await state.clear()
        text = t_for(user_id, "SUPPORT_UPDATED") + "\n\n" + t_for(user_id, "ADMIN_PANEL_TITLE")
        keyboard = _get_admin_panel_keyboard(user_id)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer(t_for(user_id, "ALERT_UPDATED"))
    elif action == "cancel_support":
        await state.clear()
        text = t_for(user_id, "ADMIN_PANEL_TITLE")
        keyboard = _get_admin_panel_keyboard(user_id)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer(t_for(user_id, "ALERT_CANCELLED"))

@router.callback_query(F.data.startswith("card_toggle_"))
async def card_toggle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return
    try:
        cid = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer()
        return
    cards = await db.list_cards()
    found = next((c for c in cards if c[0] == cid), None)
    if not found:
        await callback.answer(t_for(user_id, "ALERT_CARD_NOT_FOUND"), show_alert=True)
        return
    is_active = found[2] == 1
    await db.set_card_active(cid, not is_active)
    await callback.answer(t_for(user_id, "ALERT_UPDATED"))
    await _send_manage_cards(callback.message, user_id, replace=True)

@router.callback_query(F.data.startswith("card_delete_"))
async def card_delete_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer(t_for(user_id, "ALERT_NOT_AUTHORIZED"), show_alert=True)
        return
    try:
        cid = int(callback.data.split("_")[2])
    except Exception:
        await callback.answer()
        return
    await db.delete_card(cid)
    await callback.answer(t_for(user_id, "ALERT_DELETED"))
    await _send_manage_cards(callback.message, user_id, replace=True)


@router.message(Command("stats"))
async def stats_handler(message: Message):
    user_id = message.from_user.id
    if not _is_admin(user_id):
        logger.warning(f"Unauthorized access attempt by {user_id}. Expected Admin: {ADMIN_ID}")
        await message.answer(t_for(user_id, "NOT_AUTHORIZED"))
        return

    data = await db.get_stats()
    await message.answer(
        t_for(user_id, "STATS_TITLE") + "\n\n" +
        t_for(user_id, "STATS_DETAILS", **data),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith(("approve_", "reject_")))
async def admin_decision_handler(callback: CallbackQuery, bot: Bot):
    # Admin is clicking, so we need admin's language for the button updates/responses to admin
    admin_id = callback.from_user.id
    
    action, tx_id = callback.data.split("_")
    tx_id = int(tx_id)

    transaction = await db.get_transaction(tx_id)
    if not transaction:
        await callback.answer(t_for(admin_id, "ALERT_TRANSACTION_NOT_FOUND"))
        return

    user_id = transaction[1]
    amount = transaction[2]

    if action == "approve":
        await db.update_transaction_status(tx_id, "approved")
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n" + t_for(admin_id, "APPROVED_LABEL"),
            parse_mode="HTML",
            reply_markup=None,
        )
        try:
            # Notify user in their language
            await bot.send_message(
                chat_id=user_id,
                text=t_for(user_id, "NOTIFY_APPROVED", amount=amount),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

    elif action == "reject":
        await db.update_transaction_status(tx_id, "rejected")
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n" + t_for(admin_id, "REJECTED_LABEL"),
            parse_mode="HTML",
            reply_markup=None,
        )
        try:
            # Notify user in their language
            await bot.send_message(
                chat_id=user_id,
                text=t_for(user_id, "NOTIFY_REJECTED", amount=amount, tx_id=tx_id),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

    await callback.answer()


def register_admin_handlers(dp: Dispatcher):
    dp.include_router(router)

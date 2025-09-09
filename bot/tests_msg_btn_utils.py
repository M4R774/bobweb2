from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils_common import flatten


def button_labels_from_reply_markup(reply_markup: InlineKeyboardMarkup) -> List[str]:
    buttons: List[InlineKeyboardButton] = buttons_from_reply_markup(reply_markup)
    return [button.text for button in buttons]


def buttons_from_reply_markup(reply_markup: InlineKeyboardMarkup) -> List[InlineKeyboardButton]:
    if not reply_markup:
        return []
    return flatten(reply_markup.inline_keyboard)

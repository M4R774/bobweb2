from typing import List

from django.test import TestCase
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bobweb.bob.utils_common import flatten

#
# Utility functions to manage reply_markup containing buttons with inline queries
#
def buttons_from_reply_markup(reply_markup: InlineKeyboardMarkup) -> List[InlineKeyboardButton]:
    return flatten(reply_markup.inline_keyboard)


def button_labels_from_reply_markup(reply_markup: InlineKeyboardMarkup) -> List[str]:
    buttons: List[InlineKeyboardButton] = buttons_from_reply_markup(reply_markup)
    return [button.text for button in buttons]


def get_callback_data_from_buttons_by_text(buttons: List[InlineKeyboardButton], text: str) -> str:
    # get the callback_data from object in the list if it's text attribute contains given text
    return next((b.callback_data for b in buttons if text.lower() in b.text.lower()), None)


def assert_buttons_equal_to_reply_markup(test: TestCase,
                                         buttons: List[InlineKeyboardButton],
                                         reply_markup: InlineKeyboardMarkup):
    button_dict_list_from_markup = buttons_from_reply_markup(reply_markup)
    buttons_dict = [x.to_dict() for x in buttons]
    test.assertEqual(buttons_dict, button_dict_list_from_markup)
import os
from typing import List

import django
from django.test import TestCase
from telegram import ReplyMarkup, InlineKeyboardButton

from bobweb.bob.utils_common import flatten

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


#
# Utility functions to manage reply_markup containing buttons with inline queries
#
def buttons_from_reply_markup(reply_markup: ReplyMarkup) -> List[dict]:
    keyboard = reply_markup.to_dict().get('inline_keyboard')
    return flatten(keyboard)


def button_labels_from_reply_markup(reply_markup: ReplyMarkup) -> List[str]:
    buttons = buttons_from_reply_markup(reply_markup)
    return [button.get('text') for button in buttons]


def get_callback_data_from_buttons_by_text(buttons: List[dict], text: str) -> str:
    # get the callback_data from object in the list if it's text attribute contains given text
    return next((x['callback_data'] for x in buttons if text.lower() in x['text'].lower()), None)


def assert_buttons_equal_to_reply_markup(test: TestCase, buttons: List[InlineKeyboardButton], reply_markup: ReplyMarkup):
    button_dict_list_from_markup = buttons_from_reply_markup(reply_markup)
    buttons_dict = [x.to_dict() for x in buttons]
    test.assertEqual(buttons_dict, button_dict_list_from_markup)
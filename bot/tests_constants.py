from typing import List
from unittest import mock

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils_common import flatten


def button_labels_from_reply_markup(reply_markup: InlineKeyboardMarkup) -> List[str]:
    buttons: List[InlineKeyboardButton] = buttons_from_reply_markup(reply_markup)
    return [button.text for button in buttons]


def buttons_from_reply_markup(reply_markup: InlineKeyboardMarkup) -> List[InlineKeyboardButton]:
    if not reply_markup:
        return []
    return flatten(reply_markup.inline_keyboard)


class AsyncMockRaises(mock.MagicMock):
    """ Async mock that raises given exception when called"""
    def __init__(self, exception: Exception, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exception = exception

    async def __call__(self, *args, **kwargs):
        raise self.exception


class MockTestException(Exception):
    """ For then exception type is needed for testing """
    def __init__(self, *args):
        super().__init__(*args)


class TestExecutionException(Exception):
    """ When there is error in test execution """
    def __init__(self, *args):
        super().__init__(*args)

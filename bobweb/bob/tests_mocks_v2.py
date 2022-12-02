import datetime
import os
from typing import Any
from unittest.mock import MagicMock

import django
import pytz
from telegram import PhotoSize, ReplyMarkup, CallbackQuery, InlineKeyboardMarkup, Chat, User, Bot
from telegram.ext import CallbackContext
from telegram.utils.helpers import parse_file_input

from bobweb.bob import command_service
from bobweb.bob import message_handler
from bobweb.bob.tests_utils import button_labels_from_reply_markup, buttons_from_reply_markup, \
    get_callback_data_from_buttons_by_text
from bobweb.bob.utils_common import has

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


class MockChat(Chat):
    id_seq = 0

    def __init__(self,
                 id: int = id_seq + 1,
                 type: str = 'group',
                 **_kwargs: Any):
        super().__init__(id, type, **_kwargs)
        MockChat.id_seq = MockChat.id_seq + 1

        self.msg_count = 0
        self.users: list[MockUser] = []


class MockUser(User):
    id_seq = 0

    def __init__(self, id: int = id_seq +1,
                 first_name: str = chr(64 + id_seq), # 65 = 'A', 66 = 'B' ...
                 is_bot: bool = False,
                 **_kwargs: Any):
        super().__init__(id, first_name, is_bot, **_kwargs)
        MockUser.id_seq = MockUser.id_seq + 1

        self.own_updates: list[MockUpdate] = []
        self.own_messages = []


class MockBot(Bot):
    def __init__(self):
        super().__init__()
        self.tg_user.is_bot = True
        self.tg_user.username = self.tg_user.username + '_bot'


class MockUpdate:
    def __init__(self):

class MockMessage:
    def __init__(self):



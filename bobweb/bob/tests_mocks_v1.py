import datetime
import os
from typing import List
from unittest.mock import MagicMock

import django
import pytz
from telegram import PhotoSize, ReplyMarkup, CallbackQuery, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.utils.helpers import parse_file_input

from bobweb.bob import command_service
from bobweb.bob import message_handler
from bobweb.bob.tests_msg_btn_utils import button_labels_from_reply_markup, buttons_from_reply_markup, \
    get_callback_data_from_buttons_by_text
from bobweb.bob.utils_common import has
from bobweb.web.bobapp.models import Chat

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


class MockUser:
    def __init__(self):
        self.id = 1337
        self.first_name = "bob"
        self.last_name = "bobilainen"
        self.username = "bob-bot"
        self.is_bot = True

    def mention_markdown_v2(self):
        return "hello world!"


class MockChat:
    def __init__(self, broadcast_enabled=False, chat_id=1337, *args, **kwargs):
        del args, kwargs
        self.chat = Chat(chat_id, 'group')
        self.id = chat_id
        self.broadcast_enabled = broadcast_enabled


class MockBot:
    def __init__(self):
        self.sent_document = None
        self.defaults = None
        self.sent_photo = None

    def send_document(self, chat, file):
        self.sent_document = file
        print(chat, file)

    def sendMessage(self, chat, message):  # NOSONAR
        print(chat, message)

    def send_photo(self, chat_id, photo, caption):
        del chat_id, caption
        self.sent_photo = photo


class MockMessage:
    # Count and id seq of mock messages created
    message_count = 0

    def __init__(self, chat=MockChat()):
        self.date = datetime.datetime.now(pytz.UTC)
        self.text = ""
        self.reply_markup = None
        self.reply_message_text = None
        self.reply_to_message = None
        self.reply_image = None
        self.from_user = MockUser()
        MockMessage.message_count = MockMessage.message_count + 1
        self.message_id = MockMessage.message_count
        self.chat = chat
        self.chat_id = chat.id
        self.bot = MockBot()
        self.caption = None

    def reply_text(self, message, reply_markup: ReplyMarkup = None, parse_mode=None, quote=None):
        del parse_mode, quote
        self.reply_markup = reply_markup
        self.reply_message_text = message
        if has(reply_markup):
            print(message + '\nBUTTONS: ' + str(button_labels_from_reply_markup(reply_markup)))
        else:
            print(message)
        return self

    # reply_markdown_v2 doesn't work for some reason
    def reply_markdown(self, message, quote=None):
        del quote
        self.reply_message_text = message
        print(message)
        return self

    def reply_photo(self, image, caption, parse_mode=None, quote=None):
        del parse_mode, quote
        photo = parse_file_input(image, PhotoSize, filename=caption)
        self.reply_image = photo
        self.reply_message_text = caption
        self.caption = caption
        print(caption)
        return self

    def reply_media_group(self, media: List['InputMediaPhoto'], quote: bool):
        """ Mocks Telegram API's reply_media_group. This mock implementation only sends first image in the media
            group with its caption using another mock method """
        self.reply_photo(media[0].media, media[0].caption, quote=quote)

    def edit_text(self, text: str, reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup([]), *args, **kwargs):
        if has(text) and text != '':
            self.reply_message_text = text
        self.reply_markup = reply_markup
        print(text)
        return self

    def edit_reply_markup(self, reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup([]), *args, **kwargs):
        self.reply_markup = reply_markup
        return self


class MockUpdate:
    def __init__(self, message: MockMessage = None, edited_message: MockMessage = None):
        self.bot = MockBot()
        self.date = datetime.datetime.now(pytz.UTC)
        self.effective_user = MockUser()
        self.effective_chat = MockChat()
        self.callback_query = None
        if message is None:
            message = MockMessage()

        if has(edited_message):
            self.edited_message = edited_message
            self.effective_message = edited_message
        else:
            self.effective_message = message
            self.edited_message = None

    # Emulates message sent by a user
    def send_text(self, text: str, date=None, context: CallbackContext = None):
        if date is None:
            date = self.date
        self.callback_query = None
        self.effective_message.text = text
        self.effective_message.date = date
        message_handler.handle_update(self, context)
        return self

    def edit_message(self, text: str, context: CallbackContext = None):
        self.effective_message.text = text
        self.edited_message = self.effective_message
        message_handler.handle_update(self, context)
        return self

    # Emulates callback_query sent by user (pressing a inlineMarkup button)
    def press_button(self, label: str):
        buttons = buttons_from_reply_markup(self.effective_message.reply_markup)
        callback_data = get_callback_data_from_buttons_by_text(buttons, label)

        if callback_data is None:
            raise Exception('callback_data should not be None. Check that the buttons are as expected')

        mock_callback_query = MagicMock(spec=CallbackQuery)
        mock_callback_query.data = callback_data
        self.callback_query = mock_callback_query
        self.effective_message.text = None
        command_service.instance.reply_and_callback_query_handler(self)
        return self

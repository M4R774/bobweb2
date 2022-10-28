import datetime
import os
import random
import string
import sys
from bobweb.bob import main
from typing import List, Union, Any
from unittest import TestCase

from telegram import Message, PhotoSize, Update, ReplyMarkup
from telegram.utils.helpers import parse_file_input

from bobweb.bob import message_handler
from bobweb.bob.command import ChatCommand

import django

from bobweb.bob.utils_common import has

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from bobweb.web.bobapp.models import Chat


# Bob should reply anything to given message
def assert_has_reply_to(test: TestCase, message_text: string):
    update = MockUpdate().send_text(message_text)
    test.assertIsNotNone(update.message.reply_message_text)


# Bob should not reply to given message
def assert_no_reply_to(test: TestCase, message_text: string):
    update = MockUpdate().send_text(message_text)
    test.assertIsNone(update.message.reply_message_text)


# Bobs message should contain all given elements in the list
def assert_reply_contains(test: TestCase, message_text: string, expected_list: List[str]):
    update = MockUpdate().send_text(message_text)
    test.assertIsNotNone(update.message.reply_message_text)
    for expected in expected_list:
        test.assertRegex(update.message.reply_message_text, r'' + expected)


# Bobs message should contain all given elements in the list
def assert_reply_not_containing(test: TestCase, message_text: string, expected_list: List[type(string)]):
    update = MockUpdate().send_text(message_text)
    test.assertIsNotNone(update.message.reply_message_text)
    for expected in expected_list:
        test.assertNotRegex(update.message.reply_message_text, r'' + expected)


# Reply should be strictly equal to expected text
def assert_reply_equal(test: TestCase, message_text: string, expected: string):
    update = MockUpdate().send_text(message_text)
    test.assertEqual(expected, update.message.reply_message_text)


# Test Command.get_parameters(message) for given command
def assert_get_parameters_returns_expected_value(test: TestCase, command_text: str, command: ChatCommand):
    message = f'{command_text} test . test/test-test\ntest\ttest .vai test \n '
    parameter_expected = 'test . test/test-test\ntest\ttest .vai test'
    parameter_actual = command.get_parameters(message)
    test.assertEqual(parameter_expected, parameter_actual)


#
# Daily Question test utils
#
def buttons_from_reply_markup(reply_markup: ReplyMarkup) -> List[dict]:
    keyboard = reply_markup.to_dict().get('inline_keyboard')
    button_array = keyboard[0]
    return [button for button in button_array]


def button_labels_from_reply_markup(reply_markup: ReplyMarkup) -> List[str]:
    buttons = buttons_from_reply_markup(reply_markup)
    return [button.get('text') for button in buttons]


def always_last_choice(values):
    return values[-1]


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
    def __init__(self, broadcast_enabled=False, *args, **kwargs):
        del args, kwargs
        self.chat = Chat(1337, 'group')
        self.id = 1337
        self.broadcast_enabled = broadcast_enabled


class MockChatMember:
    def __init__(self, chat=1337, tg_user=1337, rank=0, prestige=0, message_count=0, admin=False, latest_weather_city=None):
        self.chat = chat
        self.tg_user = tg_user,
        self.rank = rank,
        self.prestige = prestige,
        self.message_count = message_count,
        self.admin = admin,
        self.latest_weather_city = latest_weather_city


class MockEntity:
    def __init__(self):
        self.type = ""


class MockBot:
    def __init__(self):
        self.sent_document = None
        self.defaults = None
        self.sent_photo = None

    def send_document(self, chat, file):
        self.sent_document = file
        print(chat, file)

    def sendMessage(self, chat, message):
        print(chat, message)

    def send_photo(self, chat_id, photo, caption):
        del chat_id, caption
        self.sent_photo = photo


class MockMessage:
    def __init__(self, chat=MockChat()):
        self.message: Message = Message(int(random.random()), datetime.datetime.now(), chat)  # NOSONAR
        self.date = datetime.datetime.now()
        self.text = "/käyttäjät"
        self.reply_markup = None
        self.reply_message_text = None
        self.reply_to_message = None
        self.reply_image = None
        self.from_user = None
        self.message_id = None
        self.chat = chat
        self.bot = MockBot()

    def reply_text(self, message, reply_markup: ReplyMarkup = None, parse_mode=None, quote=None):
        del parse_mode, quote
        self.reply_markup = reply_markup
        self.reply_message_text = message
        print(message)

    # reply_markdown_v2 doesn't work for some reason
    def reply_markdown(self, message, quote=None):
        del quote
        self.reply_message_text = message
        print(message)

    def reply_photo(self, image, caption, parse_mode=None, quote=None):
        del parse_mode, quote
        photo: Union[str, 'InputFile', Any] = parse_file_input(image, PhotoSize, filename=caption)
        self.reply_image = photo
        self.reply_message_text = caption
        print(caption)


class MockUpdate:
    def __init__(self, message: MockMessage = None, edited_message: MockMessage = None):
        self.bot = MockBot()
        self.date = datetime.datetime.now()
        self.effective_user = MockUser()
        self.effective_chat = MockChat()
        if has(edited_message):
            self.edited_message = edited_message
            self.effective_message = edited_message
            self.message = None
        else:
            self.message = message if has(message) else MockMessage(self.effective_chat.chat)
            self.effective_message = self.message
            self.edited_message = None

    def send_text(self, text):
        self.message.text = text
        message_handler.message_handler(self)
        return self


class MockResponse:
    def __init__(self, status_code=0, content=''):
        self.status_code = status_code
        self.content = content

    def json(self):
        return self.content


def mock_get_chat_member(*args, **kwargs) -> MockChatMember:
    return MockChatMember(*args, **kwargs)


# Can be used as a mock for example with '@mock.patch('requests.post', mock_request_200)'
def mock_response_200(*args, **kwargs) -> MockResponse:
    del args, kwargs
    return MockResponse(status_code=200, content='test')


# Returns a lambda function that when called returns mock response with given status code
# Example usage: 'with mock.patch('requests.post', mock_response_with_code(404))'
def mock_response_with_code(status_code=0, content=''):
    return lambda *args, **kwargs: MockResponse(status_code=status_code, content=content)

import datetime
import os
import random
import string
import sys
import main
from typing import List, Union, Any
from unittest import TestCase

from telegram import Message, PhotoSize
from telegram.utils.helpers import parse_file_input

from bob import message_handler
from bob.resources.test.images_base64_dummy import base64_dummy_images

sys.path.append('../web')  # needed for sibling import
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from bobapp.models import Chat


def assert_has_reply_to(test: TestCase, message_text: string):
    update = MockUpdate().send_text(message_text)
    test.assertIsNotNone(update.message.reply_message_text)


def assert_no_reply_to(test: TestCase, message_text: string):
    update = MockUpdate().send_text(message_text)
    test.assertIsNone(update.message.reply_message_text)


def assert_reply_contains(test: TestCase, message_text: string, expected_list: List[type(string)]):
    update = MockUpdate().send_text(message_text)
    for expected in expected_list:
        test.assertRegex(update.message.reply_message_text, r'' + expected)


def assert_reply_not_containing(test: TestCase, message_text: string, expected_list: List[type(string)]):
    update = MockUpdate().send_text(message_text)
    for expected in expected_list:
        test.assertNotRegex(update.message.reply_message_text, r'' + expected)


def assert_reply_equal(test: TestCase, message_text: string, expected: string):
    update = MockUpdate().send_text(message_text)
    test.assertEqual(expected, update.message.reply_message_text)


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
    def __init__(self):
        self.chat = Chat(1337, 'group')
        self.id = 1337


class MockEntity:
    def __init__(self):
        self.type = ""


class MockBot:
    def __init__(self):
        self.sent_document = None
        self.defaults = None

    def send_document(self, chat, file):
        self.sent_document = file
        print(chat, file)

    def sendMessage(self, chat, message):
        print(chat, message)

    def send_photo(self, chat_id, photo, caption):
        self.sent_photo = photo


class MockMessage:
    def __init__(self, chat: Chat):
        self.message: Message = Message(int(random.random()), datetime.datetime.now(), chat)
        self.text = "/käyttäjät"
        self.reply_message_text = None
        self.reply_to_message = None
        self.reply_image = None
        self.from_user = None
        self.message_id = None
        self.chat = MockChat()
        self.bot = MockBot()

    def reply_text(self, message, parse_mode=None, quote=None):
        self.reply_message_text = message
        print(message)

    # reply_markdown_v2 doesn't work for some reason
    def reply_markdown(self, message, quote=None):
        self.reply_message_text = message
        print(message)

    def reply_photo(self, image, caption, parse_mode=None, quote=None):
        photo: Union[str, 'InputFile', Any] = parse_file_input(image, PhotoSize, filename=caption)
        self.reply_image = photo
        self.reply_message_text = caption
        print(caption)


class MockUpdate:
    def __init__(self):
        self.bot = MockBot()
        self.effective_user = MockUser()
        self.effective_chat = MockChat()
        self.message = MockMessage(self.effective_chat.chat)

    def send_text(self, text):
        self.message.text = text
        message_handler.message_handler(self)
        return self


class MockResponse:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content


# Can be used as a mock for example with '@mock.patch('requests.post', mock_request_200)'
def mock_response_200(*args, **kwargs):
    return MockResponse(
        status_code=200,
        content=str.encode(f'{{"images": {base64_dummy_images},"version":"mega-bf16:v0"}}\n')
    )


def mock_response_403(*args, **kwargs):
    return MockResponse(status_code=403, content='forbidden')

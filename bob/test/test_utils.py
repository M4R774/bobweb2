import string
import sys
from typing import List
from unittest import TestCase

sys.path.append('../')  # needed for sibling import
from bob.test_main import MockUpdate


def assert_has_reply_to(test: TestCase, message_text):
    update = MockUpdate().send_text(message_text)
    test.assertIsNotNone(update.message.reply_message_text)


def assert_no_reply_to(test: TestCase, message_text):
    update = MockUpdate().send_text(message_text)
    test.assertIsNone(update.message.reply_message_text)


def assert_reply_contains(test: TestCase, message_text, expected_list: List[type(string)]):
    update = MockUpdate().send_text(message_text)
    for expected in expected_list:
        test.assertRegex(update.message.reply_message_text, r'' + expected)


def assert_reply_not_containing(test: TestCase, message_text, expected_list: List[type(string)]):
    update = MockUpdate().send_text(message_text)
    for expected in expected_list:
        test.assertNotRegex(update.message.reply_message_text, r'' + expected)

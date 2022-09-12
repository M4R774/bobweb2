import os

import main
from unittest import TestCase

import message_handler
from resources.bob_constants import PREFIXES_MATCHER
from test_main import MockUpdate

from utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_contains


class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python ../web/manage.py migrate")

    def test_command_should_reply(self):
        assert_has_reply_to(self, "/help")

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, "help")

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, "test /help")

    def test_text_after_command_no_reply(self):
        assert_no_reply_to(self, "/help test")

    def test_contains_heading_and_footer(self):
        message_start = ['Bob-botti osaa auttaa ainakin seuraavasti']
        table_headings = ['Komento', 'Selite']
        footer = ['[!./]']
        assert_reply_contains(self, ".help", message_start + table_headings + footer)

    def test_help_command_all_prefixes(self):
        update = MockUpdate()

        for prefix in ['!', '.', '/']:
            update.message.text = prefix + "help"
            message_handler.message_handler(update=update)
            self.assertRegex(update.message.reply_message_text, r'Komento\s*| Selite')

    def test_all_commands_except_help_have_help_text_defined(self):
        for command in message_handler.commands():
            if command.name != 'help':
                self.assertIsNotNone(command.help_text_short)
                self.assertEqual(len(command.help_text_short), 2)  # Tuple has 2 items - name and description
                self.assertRegex(command.help_text_short[0], r'' + command.name)

    def test_all_commands_included_in_help_response(self):
        update = MockUpdate()
        update.message.text = "!help"
        message_handler.message_handler(update=update)
        reply = update.message.reply_message_text

        for command in message_handler.commands():
            if command.name != 'help' and command.help_text_short is not None:
                # regex: linebreak followed by optional (.. ), optional command prefix, followed by command name
                self.assertRegex(reply, r'(\r\n|\r|\n)(.. )?' + PREFIXES_MATCHER + '?' + command.name)

    def test_each_row_should_be_28_chars_at_most(self):
        update = MockUpdate()
        update.message.text = "!help"
        message_handler.message_handler(update=update)
        reply = update.message.reply_message_text

        help_array = reply.split('\n\n')[1]
        expected_length_max = 28
        for row in help_array.split('\n'):
            self.assertLessEqual(expected_length_max, len(row), f'Expected length <= 28. Row: "{row}"')


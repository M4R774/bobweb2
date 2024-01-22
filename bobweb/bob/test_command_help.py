import os

import django
import pytest
from django.core import management

from bobweb.bob import main, command_service
from django.test import TestCase

from bobweb.bob import message_handler
from bobweb.bob.command_help import HelpCommand
from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER
from bobweb.bob.tests_mocks_v1 import MockUpdate

from bobweb.bob.tests_utils import assert_reply_to_contain, \
    assert_command_triggers


@pytest.mark.asyncio
class Test(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(Test, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/help', '!help', '.help', '/HELP']
        should_not_trigger = ['help', 'test /help', '/help test']
        await assert_command_triggers(self, HelpCommand, should_trigger, should_not_trigger)

    async def test_contains_heading_and_footer(self):
        message_start = ['Bob-botti osaa auttaa ainakin seuraavasti']
        table_headings = ['Komento', 'Selite']
        footer = ['[!./]']
        await assert_reply_to_contain(self, ".help", message_start + table_headings + footer)

    async def test_help_command_all_prefixes(self):
        update = MockUpdate()

        for prefix in ['!', '.', '/']:
            update.effective_message.text = prefix + "help"
            await message_handler.handle_update(update=update)
            self.assertRegex(update.effective_message.reply_message_text, r'Komento\s*| Selite')

    async def test_all_commands_except_help_have_help_text_defined(self):
        for command in command_service.instance.commands:
            if command.name not in ['help', 'ip']:
                self.assertIsNotNone(command.help_text_short)
                self.assertEqual(len(command.help_text_short), 2)  # Tuple has 2 items - name and description
                self.assertRegex(command.help_text_short[0], r'' + command.name)

    async def test_all_commands_included_in_help_response(self):
        update = MockUpdate()
        update.effective_message.text = "!help"
        await message_handler.handle_update(update=update)
        reply = update.effective_message.reply_message_text

        for command in command_service.instance.commands:
            if command.name != 'help' and command.help_text_short is not None:
                # regex: linebreak followed by optional (.. ), optional command prefix, followed by command name
                self.assertRegex(reply, r'(\r\n|\r|\n)(.. )?' + PREFIXES_MATCHER + '?' + command.name)

    async def test_each_row_should_be_28_chars_at_most(self):
        update = MockUpdate()
        update.effective_message.text = "!help"
        await message_handler.handle_update(update=update)
        reply = update.effective_message.reply_message_text

        help_array = reply.split('\n\n')[1]
        expected_length_max = 28
        for row in help_array.split('\n'):
            self.assertLessEqual(expected_length_max, len(row), f'Expected length <= 28. Row: "{row}"')


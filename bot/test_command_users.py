import datetime
import os
import random

import django
import pytest
from django.core import management
from django.test import TestCase
from unittest import mock

from bot import command_users
from bot.utils_format import transpose, MessageArrayFormatter
from bot.commands.users import create_member_array, UsersCommand
from bot.tests_utils import assert_reply_to_contain, \
    assert_reply_to_not_contain, assert_command_triggers

from web.bobapp.models import ChatMember, Chat


@pytest.mark.asyncio
class CommandUsersTest(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(CommandUsersTest, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/käyttäjät', '!käyttäjät', '.käyttäjät', '/KÄYTTÄJÄT', '/kayttajat']
        should_not_trigger = ['käyttäjät', 'test /käyttäjät', '/help käyttäjät']
        await assert_command_triggers(self, UsersCommand, should_trigger, should_not_trigger)

    async def test_contains_heading_and_footer(self):
        message_start = ['Käyttäjät \U0001F913\n\n']
        table_headings = ['Nimi', 'A', 'K', 'V']
        footer = ['A=Arvo, K=Kunnia, V=Viestit']
        await assert_reply_to_contain(self, ".käyttäjät", message_start + table_headings + footer)

    @mock.patch('bot.database.get_chat_members_for_chat')
    async def test_should_not_contain_bots(self, mock_get_members):
        member1 = create_mock_chat_member('member_1', 6, 7, 4)
        member_bot = create_mock_chat_member('member_bot', 6, 7, 4)
        mock_get_members.return_value = [member1, member_bot]

        await assert_reply_to_contain(self, ".käyttäjät", [member1.tg_user])
        await assert_reply_to_not_contain(self, ".käyttäjät", [member_bot.tg_user])

    async def test_create_member_array_sorted(self):
        member1 = create_mock_chat_member('A', 6, 7, 4)
        member2 = create_mock_chat_member('B', 6, 7, 8)
        member3 = create_mock_chat_member('C', 12, 1, 8)
        actual = create_member_array([member1, member2, member3])
        # expects the array to be sorted
        expected = [['C', 12, 1, 8],
                    ['B', 6, 7, 8],
                    ['A', 6, 7, 4]]
        self.assertEqual(expected, actual)

    async def test_format_member_array(self):
        formatter = MessageArrayFormatter('⌇ ', '~',)
        members = [create_mock_chat_member('userWithLongName', 23, 0, 1234),
                   create_mock_chat_member('user2', 1, 12, 55555)]
        members_array = create_member_array(members)
        headings = ['Nimi', 'A', 'K', 'V']
        members_array.insert(0, headings)
        actual = formatter.format(members_array)
        expected = ('Nimi            ⌇  A⌇  K⌇     V\n'
                    '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n'
                    'userWithLongName⌇ 23⌇  0⌇  1234\n'
                    'user2           ⌇  1⌇ 12⌇ 55555\n')
        self.assertEqual(expected, actual)

    async def test_create_message_board_daily_message(self):
        members = [create_mock_chat_member('userWithLongName', 23, 0, 1234),
                   create_mock_chat_member('user2', 1, 12, 55555)]
        mock_chat: Chat = Chat()
        mock_chat.leet_enabled = True
        mock_chat.latest_leet = datetime.datetime.now()

        with (mock.patch('bot.database.get_chat_members_for_chat', return_value=members),
              mock.patch('bot.database.get_chat', return_value=mock_chat)):
            message_board_message = await command_users.create_message_board_msg(None, -1)

            expected = ('Käyttäjät 🤓\n'
                        '\n'
                        '```\n'
                        'Nimi         ⌇  A⌇  K⌇     V\n'
                        '============================\n'
                        'userWithLon..⌇ 23⌇  0⌇  1234\n'
                        'user2        ⌇  1⌇ 12⌇ 55555\n'
                        '```\n'
                        'A=Arvo, K=Kunnia, V=Viestit')
            self.assertEqual(expected, message_board_message.body)
            self.assertEqual(None, message_board_message.preview)

    async def test_create_message_board_daily_message_chat_has_no_previous_leet(self):
        members = [create_mock_chat_member('userWithLongName', 23, 0, 1234)]
        mock_chat: Chat = Chat()

        with (mock.patch('bot.database.get_chat_members_for_chat', return_value=members),
              mock.patch('bot.database.get_chat', return_value=mock_chat)):
            message_board_message = await command_users.create_message_board_msg(None, -1)
            self.assertEqual(None, message_board_message)

    async def test_format_member_array_truncation(self):
        maximum_row_width = 28
        formatter = MessageArrayFormatter('⌇ ', '~', )\
            .with_truncation(maximum_row_width=maximum_row_width, column_to_trunc=0)

        members = [create_mock_chat_member('1234567890', 12345, 1234, 1234),
                   create_mock_chat_member('12345', 1, 12, 1234)]
        members_array = create_member_array(members)

        headings = ['Nimi', 'A', 'K', 'V']
        members_array.insert(0, headings)
        actual = formatter.format(members_array)

        # First username should be truncated to limit row characters to 28
        expected = 'Nimi     ⌇     A⌇    K⌇    V\n' \
                   + '~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n' \
                   + '1234567..⌇ 12345⌇ 1234⌇ 1234\n' \
                   + '12345    ⌇     1⌇   12⌇ 1234\n'
        self.assertEqual(expected, actual)

        # Make sure that no row contains more characters than
        rows = actual.split('\n')
        for row in rows:
            self.assertLessEqual(len(row), maximum_row_width)

    async def test_transpose(self):
        array = get_simple_test_array()
        actual = transpose(array)
        expected = [['123', 'a'], ['1', 12345]]
        self.assertEqual(expected, actual)

        array = get_multi_format_test_array()
        actual = transpose(array)
        expected = [['heading123', 'a',        'asd'],
                    ['heading',    123,        (1, 2)],
                    ['h',          None,       [1, 2]],
                    ['==',         '12345678', None]]  # last row missing element becomes None
        self.assertEqual(expected, actual)

    async def test_calculate_content_length_max_for_columns(self):
        formatter = MessageArrayFormatter('⌇', '=')
        array = get_simple_test_array()
        actual = formatter.calculate_content_length_max_for_columns(array)
        expected = [3, 5]
        self.assertEqual(expected, actual)

        # Without truncation
        array = get_multi_format_test_array()
        actual = formatter.calculate_content_length_max_for_columns(array)
        expected = [10, 7, 6, 8]
        self.assertEqual(expected, actual)

        # With truncation
        formatter.with_truncation(maximum_row_width=28, column_to_trunc=0)
        actual = formatter.calculate_content_length_max_for_columns(array)
        expected = [4, 7, 6, 8]
        self.assertEqual(expected, actual)


def get_simple_test_array():
    return [['123', '1'],
            ['a', 12345]]  # last row is one element shorter


def get_multi_format_test_array():
    return [['heading123', 'heading',          'h',      '=='],
            ['a',        123,             None,     '12345678'],
            ['asd',      (1, 2), [1, 2]]]  # last row is one element shorter


def create_mock_chat_member(
        tg_user_name=str(random.randint(1, 10000)),  # NOSONAR
        rank=random.randint(1, 50),  # NOSONAR
        prestige=random.randint(1, 10),  # NOSONAR
        message_count=random.randint(1, 10000)):  # NOSONAR
    member = mock.Mock(spec=ChatMember)
    member.tg_user = tg_user_name
    member.rank = rank
    member.prestige = prestige
    member.message_count = message_count
    return member

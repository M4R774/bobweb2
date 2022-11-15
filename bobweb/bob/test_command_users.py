import os
import random

from unittest import TestCase, mock

from bobweb.bob.utils_format import transpose, MessageArrayFormatter
from bobweb.bob.command_users import create_member_array
from bobweb.bob.utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_to_contains, \
    assert_reply_to_not_containing

from bobweb.web.bobapp.models import ChatMember


class Test(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python bobweb/web/manage.py migrate")

    def test_command_should_reply(self):
        assert_has_reply_to(self, "/käyttäjät")

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, "käyttäjät")

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, "test /käyttäjät")

    def test_text_after_command_no_reply(self):
        assert_no_reply_to(self, "/käyttäjät test")

    def test_contains_heading_and_footer(self):
        message_start = ['Käyttäjät \U0001F913\n\n']
        table_headings = ['Nimi', 'A', 'K', 'V']
        footer = ['A=Arvo, K=Kunnia, V=Viestit']
        assert_reply_to_contains(self, ".käyttäjät", message_start + table_headings + footer)


    @mock.patch('bobweb.bob.database.get_chat_members_for_chat')
    def test_should_not_contain_bots(self, mock_get_members):
        member1 = create_mock_chat_member('member_1', 6, 7, 4)
        member_bot = create_mock_chat_member('member_bot', 6, 7, 4)
        mock_get_members.return_value = [member1, member_bot]

        assert_reply_to_contains(self, ".käyttäjät", [member1.tg_user])
        assert_reply_to_not_containing(self, ".käyttäjät", [member_bot.tg_user])


    def test_create_member_array_sorted(self):
        member1 = create_mock_chat_member('A', 6, 7, 4)
        member2 = create_mock_chat_member('B', 6, 7, 8)
        member3 = create_mock_chat_member('C', 12, 1, 8)
        actual = create_member_array([member1, member2, member3])
        # expects the array to be sorted
        expected = [['C', 12, 1, 8],
                    ['B', 6, 7, 8],
                    ['A', 6, 7, 4]]
        self.assertEqual(expected, actual)

    def test_format_member_array(self):
        formatter = MessageArrayFormatter('⌇ ', '~',)
        members = [create_mock_chat_member('nimismies', 23, 0, 1234),
                   create_mock_chat_member('ukko', 1, 12, 55555)]
        members_array = create_member_array(members)
        headings = ['Nimi', 'A', 'K', 'V']
        members_array.insert(0, headings)
        actual = formatter.format(members_array)
        expected = 'Nimi     ⌇  A⌇  K⌇     V\n~~~~~~~~~~~~~~~~~~~~~~~~\nnimismies⌇ 23⌇  0⌇  1234\nukko     ⌇  1⌇ 12⌇ 55555\n'
        self.assertEqual(expected, actual, f'expected:\n{expected}\nactual:\n{actual}')

    def test_format_member_array_truncation(self):
        maximum_row_width = 28
        formatter = MessageArrayFormatter('⌇ ', '~', )\
            .with_truncation(maximum_row_width=maximum_row_width, column_to_trunc=0)

        members = [create_mock_chat_member('1234567890', 12345, 1234, 1234),
                   create_mock_chat_member('12345', 1, 12, 1234)]
        members_array = create_member_array(members)

        headings = ['Nimi', 'A', 'K', 'V']
        members_array.insert(0, headings)
        actual = formatter.format(members_array)

        # First user name should be truncated to limit row characters to 28
        expected = 'Nimi     ⌇     A⌇    K⌇    V\n' \
                   + '~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n' \
                   + '1234567..⌇ 12345⌇ 1234⌇ 1234\n' \
                   + '12345    ⌇     1⌇   12⌇ 1234\n'
        self.assertEqual(expected, actual)

        # Make sure that no row contains more characters than
        rows = actual.split('\n')
        for row in rows:
            self.assertLessEqual(len(row), maximum_row_width)

    def test_transpose(self):
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

    def test_calculate_content_length_max_for_columns(self):
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

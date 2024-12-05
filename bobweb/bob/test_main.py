import asyncio
import filecmp
import os
import datetime
from decimal import Decimal

import pytest
from django.core import management
from freezegun import freeze_time
from telegram import MessageEntity

from bobweb.bob import main, config
from pathlib import Path
from django.test import TestCase
from unittest import mock

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_aika import AikaCommand
from bobweb.bob.command_huutista import HuutistaCommand
from bobweb.bob.resources.bob_constants import fitz

from bobweb.bob import db_backup
from bobweb.bob import git_promotions
from bobweb.bob import message_handler
from bobweb.bob import database

import django

from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUpdate, MockMessage, MockBot, MockChat, \
    init_private_chat_and_user
from bobweb.bob.tests_utils import assert_command_triggers
from bobweb.bob.utils_common import split_to_chunks, flatten, \
    min_max_normalize, find_start_indexes, split_text_keep_text_blocks

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from bobweb.web.bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser


@pytest.mark.asyncio
class Test(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(Test, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    async def test_process_entities(self):
        chat, user = init_chat_user()  # v2 mocks
        await user.send_message('message1')

        message = MockMessage(chat=chat, from_user=user)
        message.text = f"@{user.username}"
        update = MockUpdate(message=message)

        message_entity = MessageEntity(type="mention", length=0, offset=0)
        message.entities = (message_entity,)

        await git_promotions.process_entities(update)

    async def test_empty_incoming_message(self):
        update = MockUpdate()
        update.message = None
        await message_handler.handle_update(update=update)
        self.assertEqual(update.effective_message, None)

    async def test_leet_command(self):
        chat, user = init_chat_user()  # v2 mocks
        user.username = 'bob-bot'
        # Time stamps are set as utc+-0 time as Telegram api uses normalized time for messages
        # As dates are in 1.1.1970, it is standard time in Finnish time zone and daylight savings time
        # does not need to be considered
        dt = datetime.datetime(1970, 1, 1, 1, 1)

        with freeze_time(dt.replace(hour=10, minute=37)):
            await user.send_message('1337')
            self.assertIn("siviilipalvelusmies. 🔽", chat.last_bot_txt())

        with freeze_time(dt.replace(hour=10, minute=36)):
            await user.send_message('1337')
            self.assertIn("siviilipalvelusmies. 🔽", chat.last_bot_txt())

        with freeze_time(dt.replace(hour=11, minute=37)):
            await user.send_message('1337')
            self.assertIn("alokas! 🔼 Lepo. ", chat.last_bot_txt())

        with freeze_time(dt.replace(hour=10, minute=38)):
            await user.send_message('1337')
            self.assertIn("siviilipalvelusmies. 🔽", chat.last_bot_txt())

        # Gain rank 51 times. Gives 1 prestige + 12 ranks on the next prestige
        for i in range(51):
            with freeze_time(dt.replace(year=1970 + i, hour=11, minute=37)):
                await user.send_message('1337')
        self.assertIn("pursimies! 🔼 Lepo.", chat.last_bot_txt())

        chat_member: ChatMember = ChatMember.objects.get(chat=chat.id, tg_user=user.id)
        self.assertEqual(1, chat_member.prestige)
        self.assertEqual(12, chat_member.rank)

        with freeze_time(dt.replace(hour=11, minute=38)):
            for i in range(15):
                await user.send_message('1337')

        self.assertIn("siviilipalvelusmies. 🔽", chat.last_bot_txt())

        chat_member: ChatMember = ChatMember.objects.get(chat=chat.id, tg_user=user.id)
        self.assertEqual(1, chat_member.prestige)
        self.assertEqual(0, chat_member.rank)

        # Test that works when daylight savings time is active in default timezone. DST usage started in 1981
        with freeze_time(datetime.datetime(1982, 7, 1, 10, 37)):
            await user.send_message('1337')
            self.assertIn("alokas! 🔼 Lepo.", chat.last_bot_txt())

    async def test_aika_command_triggers(self):
        should_trigger = ['/aika', '!aika', '.aika', '/Aika', '/aikA']
        should_not_trigger = ['aika', '.aikamoista', 'asd /aika', '/aika asd']
        await assert_command_triggers(self, AikaCommand, should_trigger, should_not_trigger)

    async def test_time_command(self):
        chat, user = init_chat_user()  # v2 mocks
        await user.send_message("/aika")
        hours_now = str(datetime.datetime.now(fitz).strftime('%H'))
        hours_regex = r"\b" + hours_now + r":"
        self.assertRegex(chat.last_bot_txt(), hours_regex)

    async def test_low_probability_reply(self):
        chat, user = init_chat_user()  # v2 mocks

        # Assert no reaction from bot
        with mock.patch('random.randint', lambda *args: 0):
            await user.send_message("Anything")
        self.assertEqual(0, len(chat.bot.messages))

        # Now with certain probability send another message, should trigger
        with mock.patch('random.randint', lambda *args: 1):
            await user.send_message("Feeling lucky")

        expected_bot_message_count = 1
        self.assertEqual(expected_bot_message_count, len(chat.bot.messages))
        self.assertIn('olette todella onnekas 🍀', chat.last_bot_txt())

        # Now make sure, that user is not lucky
        with mock.patch('random.randint', lambda *args: 0):
            await user.send_message("Not lucky")

        # No new messages from bot so same message count as before
        self.assertEqual(expected_bot_message_count, len(chat.bot.messages))

    async def test_promote_committer_or_find_out_who_he_is(self):
        chat = MockChat()
        os.environ["COMMIT_AUTHOR_NAME"] = "bob"
        os.environ["COMMIT_AUTHOR_NAME"] = "bob@bob.com"
        await git_promotions.promote_committer_or_find_out_who_he_is(chat.bot)

    def test_get_git_user_and_commit_info(self):
        git_promotions.get_git_user_and_commit_info()

    async def test_promote_or_praise(self):
        chat, user = init_chat_user()  # v2 mocks
        await user.send_message('first')

        tg_user = TelegramUser.objects.get(id=user.id)
        git_user = GitUser(name=user.name, email=user.name, tg_user=tg_user)
        git_user.save()

        # Test when latest date should be NULL, promotion should happen
        await git_promotions.promote_or_praise(git_user, chat.bot)
        tg_user = TelegramUser.objects.get(id=user.id)
        chat_member = ChatMember.objects.get(tg_user=tg_user.id, chat=chat.id)
        self.assertEqual(1, chat_member.rank)

        # Test again, no promotion should happen
        tg_user = TelegramUser(id=user.id,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(fitz).date() -
                               datetime.timedelta(days=6))
        tg_user.save()
        await git_promotions.promote_or_praise(git_user, chat.bot)
        tg_user = TelegramUser.objects.get(id=user.id)
        self.assertEqual(tg_user.latest_promotion_from_git_commit,
                         datetime.datetime.now(fitz).date() -
                         datetime.timedelta(days=6))
        chat_member = ChatMember.objects.get(tg_user=tg_user.id, chat=chat.id)
        self.assertEqual(1, chat_member.rank)

        # Change latest promotion to 7 days ago, promotion should happen
        tg_user = TelegramUser(id=user.id,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(fitz).date() -
                               datetime.timedelta(days=7))
        tg_user.save()
        await git_promotions.promote_or_praise(git_user, chat.bot)
        chat_member = ChatMember.objects.get(tg_user=tg_user.id, chat=chat.id)
        self.assertEqual(2, chat_member.rank)

        # Check that new random message dont mess up the user database
        await user.send_message("jepou juupeli juu")

        # Test again, no promotion
        await git_promotions.promote_or_praise(git_user, chat.bot)
        tg_user = TelegramUser.objects.get(id=user.id)
        chat_member = ChatMember.objects.get(tg_user=tg_user.id, chat=chat.id)
        self.assertEqual(datetime.datetime.now(fitz).date(),
                         tg_user.latest_promotion_from_git_commit)
        self.assertEqual(2, chat_member.rank)

    async def test_huutista(self):
        chat, user = init_chat_user()  # v2 mocks
        await user.send_message("Huutista")
        self.assertEqual("...joka tuutista! 😂", chat.last_bot_txt())

    async def test_huutista_command_triggers(self):
        # Case-insensitive, but the message cannot contain anything else
        should_trigger = ['HUUTISTA', 'huutista', 'hUuTiStA']
        should_not_trigger = ['/huutista', 'Huutista tälle', 'sinne huutista', 'huutistatuutista']
        await assert_command_triggers(self, HuutistaCommand, should_trigger, should_not_trigger)

    async def test_db_updaters_command(self):
        chat, chat_user = init_chat_user()  # v2 mocks
        await chat_user.send_message('message')

        user_from_db = TelegramUser.objects.get(id=chat_user.id)
        self.assertEqual(chat_user.username, user_from_db.username)
        self.assertEqual(chat_user.first_name, user_from_db.first_name)
        self.assertEqual(chat_user.last_name, user_from_db.last_name)
        chat_member_from_db = ChatMember.objects.get(tg_user=chat_user.id, chat=chat.id)
        self.assertEqual(1, chat_member_from_db.message_count)

    async def test_init_bot(self):
        config.bot_token = "DUMMY_ENV_VAR"
        main.init_bot_application()

    async def test_backup_create(self):
        chat, user = init_private_chat_and_user()  # v2 mocks
        await user.send_message('message')
        chat_entity = database.get_chat(chat_id=chat.id)
        chat_entity.broadcast_enabled = True
        chat_entity.save()

        # First try to create backup without global admin
        await db_backup.create(chat.bot)
        self.assertIn('global_admin ei ole asetettu', chat.last_bot_txt())

        # Now set global admin and try to create backup again
        tg_user = database.get_telegram_user(user.id)
        with mock.patch('bobweb.bob.database.get_global_admin', lambda: tg_user):
            await db_backup.create(chat.bot)
            database_path = Path('bobweb/web/db.sqlite3')
            self.assertTrue(filecmp.cmp(database_path, chat.media_and_documents[0].name, shallow=False))

    async def test_ChatCommand_get_parameters(self):
        command = ChatCommand(name='test', regex=r'^[/.!]test_command($|\s)', help_text_short=('test', 'test'))
        expected = 'this is parameters \n asd'
        actual = command.get_parameters('/test_command   \n this is parameters \n asd')
        self.assertEqual(expected, actual)

        expected = ''
        actual = command.get_parameters('/test_command')
        self.assertEqual(expected, actual)

    async def test_activity_state_no_implementation_nothing_happens(self):
        chat, user = init_chat_user()
        activity = ActivityState()
        await activity.execute_state()
        processed = await activity.preprocess_reply_data_hook('asd')
        await activity.handle_response(None, 'asd')
        # Nothing has been returned and no messages have been sent to chat
        self.assertEqual('asd', processed)
        self.assertSequenceEqual([], chat.messages)

    async def test_split_to_chunks_basic_cases(self):
        iterable = [0, 1, 2, 3, 4, 5, 6, 7]
        chunk_size = 3
        expected = [[0, 1, 2], [3, 4, 5], [6, 7]]
        self.assertEqual(expected, split_to_chunks(iterable, chunk_size))

        iterable = []
        chunk_size = 3
        expected = []
        self.assertEqual(expected, split_to_chunks(iterable, chunk_size))

        iterable = ['a', 'b', 'c', 'd']
        chunk_size = 1
        expected = [['a'], ['b'], ['c'], ['d']]
        self.assertEqual(expected, split_to_chunks(iterable, chunk_size))

        iterable = None
        chunk_size = 1
        expected = []
        self.assertEqual(expected, split_to_chunks(iterable, chunk_size))

        iterable = ['a', 'b', 'c', 'd']
        chunk_size = -1
        expected = []
        self.assertEqual(expected, split_to_chunks(iterable, chunk_size))

        # Tests that text can be split as well
        iterable = 'abcd efg'
        chunk_size = 3
        expected = ['abc', 'd e', 'fg']
        self.assertEqual(expected, split_to_chunks(iterable, chunk_size))

    async def test_flatten(self):
        list_of_lists = [[[[]]], [], [[]], [[], []]]
        self.assertEqual([], flatten(list_of_lists))

        list_of_lists_with_items = [[1], [2, 3], [4, [5, [6, [7, [8]]]]]]
        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8], flatten(list_of_lists_with_items))

        self.assertIsNone(flatten(None))  # If called with None, should return None
        self.assertEqual('abc', flatten('abc'))

    async def test_min_max_normalize_simple_case_single_value(self):
        original_min, original_max = 0, 10
        original_value = 3

        new_min, new_max = 0, 1
        expected_values = Decimal('0.3')
        actual_value = min_max_normalize(original_value, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

    async def test_min_max_normalize_simple_case_single_list(self):
        original_min, original_max = 0, 10
        original_values = [0, 1, 2, 3]

        new_min, new_max = 0, 25
        expected_values = [0, 2.5, 5, 7.5]
        actual_value = min_max_normalize(original_values, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

    async def test_min_max_normalize_simple_case_list_of_lists(self):
        original_min, original_max = 0, 10
        original_values = [[0, 1], [2, 3]]

        new_min, new_max = 0, 5
        expected_values = [[0, 0.5], [1, 1.5]]
        actual_value = min_max_normalize(original_values, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

    async def test_min_max_normalize_handles_scale_movement(self):
        original_min, original_max = 0, 10
        original_values = [0, 1, 2, 3]

        new_min, new_max = 50, 100
        expected_values = [50, 55, 60, 65]
        actual_value = min_max_normalize(original_values, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

    async def test_min_max_normalize_no_divizion_by_zero(self):
        """ Test case created from bug report message where decimal.DivisionByZero: [<class 'decimal.DivisionByZero'>]
            was raised from normalization_function inside min_max_normalize. """
        original_min, original_max = 0, 0
        original_values = [0, 1, 2, 3]

        new_min, new_max = 0, 0
        expected_values = [0, 0, 0, 0]
        actual_value = min_max_normalize(original_values, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

    def test_find_offsets(self):
        text = 'Test\n\n123'
        self.assertEqual(4, next(find_start_indexes(text, '\n\n')))

        text = 'Test\n\n123\n\n'
        self.assertEqual([4, 9], list(find_start_indexes(text, '\n\n')))

    def test_split_text_keep_code_blocks_only_spaces(self):
        # Basic idea. Try to keep as much intact content in each message.
        # First cases: should split at white space if able. If there is no white space inside given split range,
        # does a hard split at the limit
        text = '1234 1234 12 Bar'
        self.assertEqual(['1234 1234 12 Bar'], split_text_keep_text_blocks(text, 3, 20))
        self.assertEqual(['1234 1234 12', 'Bar'], split_text_keep_text_blocks(text, 3, 15))
        self.assertEqual(['1234 1234', '12 Bar'], split_text_keep_text_blocks(text, 3, 10))
        self.assertEqual(['1234', '1234', '12 Bar'], split_text_keep_text_blocks(text, 3, 6))

        # As a last example: When range of number of characters is 2-3, should split at last space
        # with the limit or at the end of the limit. For the 1. chunk text is '1234 1234 12 Bar'.
        # As the chunk can have at most 3 characters and there are no white spaced, split is done so that
        # first chunk is '123'. When evaluating the second chunk, the text is '4 1234 12 Bar'. Now, the
        # function starts iterating from the end limit and splits at the first space leaving only '4'
        # for the second chunk.
        self.assertEqual(['123', '4', '123', '4', '12', 'Bar'], split_text_keep_text_blocks(text, 2, 3))

    def test_split_text_keep_code_blocks_paragraphs(self):
        # Tries to keep paragraphs intact. If remaining text is longer than the limit,
        # splits text at the previous paragraph break.
        text = 'Test test\n\nFoo Bar\n\nTest test'
        expected = ['Test test', 'Foo Bar', 'Test test']
        self.assertEqual(expected, split_text_keep_text_blocks(text, 0, 10))
        expected = ['Test test\n\nFoo Bar', 'Test test']
        self.assertEqual(expected, split_text_keep_text_blocks(text, 0, 20))
        # If min character limit is higher thant the paragraph boundaries, does a split on last
        # white space before end of the limit
        expected = ['Test test\n\nFoo Bar\n\nTest', 'test']
        self.assertEqual(expected, split_text_keep_text_blocks(text, 24, 26))

    def test_split_text_keep_code_blocks_code_blocks(self):
        # Tries to keep code blocks intact. If remaining text is longer than the limit,
        # splits text at the previous code block start if one exists within the limits.
        text = 'Test test\n```Foo```\nTest test'
        expected = ['Test test', '```Foo```', 'Test test']
        self.assertEqual(expected, split_text_keep_text_blocks(text, 0, 10))
        expected = ['Test test\n```Foo```', 'Test test']
        self.assertEqual(expected, split_text_keep_text_blocks(text, 0, 20))

        # If no code block start exists within the limit, does a hard split by closing the current code block
        # and opening the next chunk with a new code block.
        text = '```\nFoo Bar\n\ntest test\n```'
        expected = ['```\nFoo Bar\n```', '```\ntest test\n```']
        self.assertEqual(expected, split_text_keep_text_blocks(text, 10, 20))

        # If message max length limit is inside code block, but the code block starts within the min and max
        # length limits, splits messages just before start of the clode block
        text = '1234567890 ```\nFoo Bar```'
        expected = ['1234567890', '```\nFoo Bar```']
        self.assertEqual(expected, split_text_keep_text_blocks(text, 8, 15))

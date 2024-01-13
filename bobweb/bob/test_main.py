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
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.common_activity_states import ContentPaginationState, create_page_labels
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_aika import AikaCommand
from bobweb.bob.command_huutista import HuutistaCommand
from bobweb.bob.resources.bob_constants import fitz

from bobweb.bob import db_backup
from bobweb.bob import git_promotions
from bobweb.bob import message_handler
from bobweb.bob import database

import django
from django.test import TestCase

from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUpdate, MockMessage, MockBot, MockChat, \
    init_private_chat_and_user
from bobweb.bob.tests_utils import assert_command_triggers
from bobweb.bob.utils_common import split_to_chunks, flatten, \
    min_max_normalize, split_text

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
        await activity.handle_response('asd')
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
        expected = ['a', 'b', 'c', 'd']
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



class TestSplitText(TestCase):
    def test_basic_split(self):
        text = 'Mary had a little lamb and it was called Daisy'
        limit = 20
        expected_chunks = ['Mary had a little', 'lamb and it was', 'called Daisy']
        actual_chunks = split_text(text, limit)
        self.assertEqual(expected_chunks, actual_chunks)

    def test_empty_text(self):
        text = ''
        limit = 10
        expected_chunks = ['']
        actual_chunks = split_text(text, limit)
        self.assertEqual(expected_chunks, actual_chunks)

    def test_large_limit(self):
        text = 'Mary had a little lamb and it was called Daisy'
        limit = 100
        expected_chunks = ['Mary had a little lamb and it was called Daisy']
        actual_chunks = split_text(text, limit)
        self.assertEqual(expected_chunks, actual_chunks)

    def test_small_limit(self):
        text = 'Mary'
        limit = 1
        expected_chunks = ['M', 'a', 'r', 'y']
        actual_chunks = split_text(text, limit)
        self.assertEqual(expected_chunks, actual_chunks)

    def test_limit_equal_to_text_length(self):
        text = 'Mary'
        limit = 4
        expected_chunks = ['Mary']
        actual_chunks = split_text(text, limit)
        self.assertEqual(expected_chunks, actual_chunks)

    def test_should_split_if_next_character_from_limit_is_whitespace(self):
        text = 'Mary had'
        limit = 4
        expected_chunks = ['Mary', 'had']
        actual_chunks = split_text(text, limit)
        self.assertEqual(expected_chunks, actual_chunks)


class TestPagination(TestCase):

    def test_simple_cases_with_increasing_page_count(self):
        self.assertEqual(['[1]'], create_page_labels(1, 0))
        self.assertEqual(['[1]', '2'], create_page_labels(2, 0))
        self.assertEqual(['[1]', '2', '3', '4', '5'], create_page_labels(5, 0))
        self.assertEqual(['[1]', '2', '3', '4', '5', '6', '7'], create_page_labels(7, 0))
        self.assertEqual(['[1]', '2', '3', '4', '5', '6', '>>'], create_page_labels(10, 0))

    def test_current_page_is_always_surrounded_with_brackets(self):
        self.assertEqual(['[1]', '2', '3', '4', '5', '6', '>>'], create_page_labels(10, 0))
        self.assertEqual(['1', '[2]', '3', '4', '5', '6', '>>'], create_page_labels(10, 1))
        self.assertEqual(['1', '2', '[3]', '4', '5', '6', '>>'], create_page_labels(10, 2))
        self.assertEqual(['1', '2', '3', '[4]', '5', '6', '>>'], create_page_labels(10, 3))

    def test_current_page_is_kept_centered_when_possible(self):
        self.assertEqual(['1', '2', '[3]', '4', '5', '6', '>>'], create_page_labels(10, 2))
        self.assertEqual(['1', '2', '3', '[4]', '5', '6', '>>'], create_page_labels(10, 3))
        self.assertEqual(['<<', '3', '4', '[5]', '6', '7', '>>'], create_page_labels(10, 4))
        self.assertEqual(['<<', '4', '5', '[6]', '7', '8', '>>'], create_page_labels(10, 5))
        self.assertEqual(['<<', '5', '6', '[7]', '8', '9', '10'], create_page_labels(10, 6))
        self.assertEqual(['<<', '5', '6', '7', '[8]', '9', '10'], create_page_labels(10, 7))
        self.assertEqual(['<<', '5', '6', '7', '8', '[9]', '10'], create_page_labels(10, 8))
        self.assertEqual(['<<', '5', '6', '7', '8', '9', '[10]'], create_page_labels(10, 9))

    def test_paginated_message_content(self):
        # Setup content for the paged
        pages = split_text('Mary had a little lamb and it was called Daisy', 20)
        self.assertEqual(['Mary had a little', 'lamb and it was', 'called Daisy'], pages)

        # Create state and use mock message handler while sending single message that just starts the activity
        state = ContentPaginationState(pages)
        with mock.patch('bobweb.bob.message_handler.handle_update', mock_activity_starter(state)):
            chat, user = init_chat_user()
            user.send_message('paginate that')

            # Now assert that the content is as expected. Should have header with page information and labels that show
            # current page and other pages
            self.assertEqual('[Sivu (1 / 3)]\nMary had a little', chat.last_bot_txt())
            labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
            self.assertEqual(['[1]', '2', '3'], labels)

            # Change page and assert content has updated as expected
            user.press_button_with_text('2', chat.last_bot_msg())

            self.assertEqual('[Sivu (2 / 3)]\nlamb and it was', chat.last_bot_txt())
            labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
            self.assertEqual(['1', '[2]', '3'], labels)

    def test_skip_to_end_and_skip_to_start_work_as_expected(self):
        pages = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']

        state = ContentPaginationState(pages)
        with mock.patch('bobweb.bob.message_handler.handle_update', mock_activity_starter(state)):
            chat, user = init_chat_user()
            user.send_message('paginate that')
            user.press_button_with_text('5', chat.last_bot_msg())

            self.assertEqual('[Sivu (5 / 10)]\n5', chat.last_bot_txt())
            labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
            self.assertEqual(['<<', '3', '4', '[5]', '6', '7', '>>'], labels)

            # Now, pressing skip to end should change page to 10
            user.press_button_with_text('>>', chat.last_bot_msg())
            self.assertEqual('[Sivu (10 / 10)]\n10', chat.last_bot_txt())

            # And pressing skip to start should change page to 1
            user.press_button_with_text('<<', chat.last_bot_msg())
            self.assertEqual('[Sivu (1 / 10)]\n1', chat.last_bot_txt())

    def test_content_with_pagination_headers_does_not_exceed_max_message_length(self):
        # This tests that given a humongous text with limit of 4076 it is pagenated
        # to pages with content shorter than Telegrams maximum message length of 4096
        content = '*** ' * 200_000  # Maximum content length described by
        pages = split_text(content, 4076)

        state = ContentPaginationState(pages)
        with mock.patch('bobweb.bob.message_handler.handle_update', mock_activity_starter(state)):
            chat, user = init_chat_user()
            user.send_message('paginate that')
            user.press_button_with_text('>>')

        self.assertLess(len(chat.last_bot_txt()), TELEGRAM_MESSAGE_MAX_LENGTH)


def mock_activity_starter(initial_state: ActivityState) -> callable:
    """ Can be used to mock MessageHandler that just creates activity with given state for each message """
    def mock_message_handler(update, context):
        activity = CommandActivity(initial_update=update, state=initial_state)
        command_service.instance.add_activity(activity)
    return mock_message_handler

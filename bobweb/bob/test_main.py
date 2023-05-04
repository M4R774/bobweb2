import filecmp
import os
import datetime
import time
from decimal import Decimal

from bobweb.bob import main
from pathlib import Path
from unittest import mock, IsolatedAsyncioTestCase
from unittest.mock import patch, Mock

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_aika import AikaCommand
from bobweb.bob.command_or import OrCommand
from bobweb.bob.command_space import SpaceCommand
from bobweb.bob.tests_mocks_v1 import MockUpdate, MockBot, MockUser, MockChat, MockMessage
from bobweb.bob.resources.bob_constants import fitz
from telegram.chat import Chat

from bobweb.bob import db_backup
from bobweb.bob import git_promotions
from bobweb.bob import message_handler
from bobweb.bob import command_leet
from bobweb.bob import database

import django

from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import mock_random_with_delay, assert_command_triggers
from bobweb.bob.utils_common import split_to_chunks, flatten, \
    min_max_normalize

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from bobweb.web.bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser


class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python bobweb/web/manage.py migrate")
        SpaceCommand.run_async = False

    def setUp(self) -> None:
        update = MockUpdate()
        update.effective_message.text = "jepou juupeli juu"
        update.effective_chat.id = 1337
        update.effective_user.id = 1337
        message_handler.handle_update(update)
        main.broadcast_and_promote(update)

    def test_reply_handler(self):
        update = MockUpdate()
        mock_chat = MockChat()
        mock_message = MockMessage(mock_chat.chat)
        mock_message.from_user = MockUser()
        mock_message.text = "Git käyttäjä bla bla blaa"
        mock_message.reply_to_message = mock_message
        update.effective_message = mock_message
        admin = TelegramUser(id=1337)
        bob = Bob(id=1, global_admin=admin)
        bob.save()

    def test_process_entity(self):
        message_entity = Mock()
        message_entity.type = "mention"

        mock_update = MockUpdate()
        mock_update.effective_message.text = "@bob-bot "
        git_promotions.process_entity(message_entity, mock_update)

        mock_update = MockUpdate()
        mock_update.effective_message.text = "@bob-bot"
        git_promotions.process_entity(message_entity, mock_update)

    def test_empty_incoming_message(self):
        update = MockUpdate()
        update.effective_message = None
        message_handler.handle_update(update=update)
        self.assertEqual(update.effective_message, None)

    def test_leet_command(self):
        update = MockUpdate()
        update.effective_message.text = "1337"

        member = ChatMember.objects.get(chat=update.effective_user.id, tg_user=update.effective_chat.id)
        member.rank = 0
        member.prestige = 0
        member.save()
        old_prestige = member.prestige

        # Time stamps are set as utc+-0 time as Telegram api uses normalized time for messages
        # As dates are in 1.1.1970, it is standard time in Finnish time zone and daylight savings time
        # does not need to be considered

        update.effective_message.date = datetime.datetime(1970, 1, 1, 10, 37)
        message_handler.handle_update(update)
        self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                         update.effective_message.reply_message_text)

        update.effective_message.date = datetime.datetime(1970, 1, 1, 11, 36)
        command_leet.leet_command(update)
        self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                         update.effective_message.reply_message_text)

        update.effective_message.date = datetime.datetime(1970, 1, 1, 11, 37)
        command_leet.leet_command(update)
        self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon alokas! 🔼 Lepo. ",
                         update.effective_message.reply_message_text)

        update.effective_message.date = datetime.datetime(1970, 1, 1, 11, 38)
        command_leet.leet_command(update)
        self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                         update.effective_message.reply_message_text)

        for i in range(51):
            update.effective_message.date = datetime.datetime(1970 + i, 1, 1, 11, 37)
            command_leet.leet_command(update)
        self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon pursimies! 🔼 Lepo. ",
                         update.effective_message.reply_message_text)

        update.effective_message.date = datetime.datetime(1970, 1, 1, 11, 38)
        for i in range(15):
            command_leet.leet_command(update)
        self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                         update.effective_message.reply_message_text)
        self.assertEqual(old_prestige+1, ChatMember.objects.get(chat=update.effective_user.id,
                                                                tg_user=update.effective_chat.id).prestige)
        self.assertEqual(0, ChatMember.objects.get(chat=update.effective_user.id,
                                                   tg_user=update.effective_chat.id).rank)

        # Test that works when daylight savings time is active in default timezone. DST usage started in 1981
        update.effective_message.date = datetime.datetime(1982, 7, 1, 10, 37)
        command_leet.leet_command(update)
        self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon alokas! 🔼 Lepo. ",
                         update.effective_message.reply_message_text)

    @mock.patch('random.choice', mock_random_with_delay)
    def test_command_to_be_handled_sync(self):
        OrCommand.run_async = False
        chat, user = init_chat_user()  # v2 mocks
        user.send_message('1 /vai 2')
        user.send_message('1337')

        time.sleep(0.1)
        # Expected to be in the same order as sent
        self.assertEqual('1', chat.bot.messages[-2].text)
        self.assertIn('Alokasvirhe!', chat.bot.messages[-1].text)

    @mock.patch('random.choice', mock_random_with_delay)
    def test_command_to_be_handled_async(self):
        OrCommand.run_async = True
        chat, user = init_chat_user()  # v2 mocks
        user.send_message('1 /vai 2')
        user.send_message('1337')

        time.sleep(0.1)
        # Now as OrCommand is handled asynchronously, leet-command should be resolved first
        self.assertIn('Alokasvirhe!', chat.bot.messages[-2].text)
        self.assertEqual('1', chat.bot.messages[-1].text)

    def test_aika_command_triggers(self):
        should_trigger = ['/aika', '!aika', '.aika', '/Aika', '/aikA']
        should_not_trigger = ['aika', '.aikamoista', 'asd /aika', '/aika asd']
        assert_command_triggers(self, AikaCommand, should_trigger, should_not_trigger)

    def test_time_command(self):
        update = MockUpdate()
        update.effective_message.text = "/aika"
        message_handler.handle_update(update=update)
        hours_now = str(datetime.datetime.now(fitz).strftime('%H'))
        hours_regex = r"\b" + hours_now + r":"
        self.assertRegex(update.effective_message.reply_message_text,
                        hours_regex)

    def test_low_probability_reply(self):
        update = MockUpdate()
        update.effective_message.text = "Anything"
        update.effective_message.reply_message_text = None
        message_handler.handle_update(update=update)
        try:
            self.assertEqual(None, update.effective_message.reply_message_text)
        except AssertionError:
            self.assertEqual("Vaikuttaa siltä että olette todella onnekas " + "\U0001F340",
                             update.effective_message.reply_message_text)

        random_int = 1
        message_handler.low_probability_reply(update=update, integer=random_int)
        self.assertEqual("Vaikuttaa siltä että olette todella onnekas " + "\U0001F340",
                         update.effective_message.reply_message_text)

        random_int = 2
        message_handler.low_probability_reply(update=update, integer=random_int)
        message_handler.low_probability_reply(update=update, integer=0)

    def test_broadcast_and_promote(self):
        update = MockUpdate()
        main.broadcast_and_promote(update)

    def test_promote_committer_or_find_out_who_he_is(self):
        update = MockUpdate()
        os.environ["COMMIT_AUTHOR_NAME"] = "bob"
        os.environ["COMMIT_AUTHOR_NAME"] = "bob@bob.com"
        git_promotions.promote_committer_or_find_out_who_he_is(update)

    def test_get_git_user_and_commit_info(self):
        git_promotions.get_git_user_and_commit_info()

    def test_promote_or_praise(self):
        mock_bot = MockBot()

        # Create tg_user, chat, chat_member and git_user
        tg_user = TelegramUser(id=1337)
        tg_user.save()
        chat = Chat(id=1337)
        chat.save()
        chat_member = ChatMember(tg_user=tg_user, chat=chat)
        try:
            chat_member.save()
        except:
            chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
            chat_member.rank = 0
            chat_member.prestige = 0
            chat_member.save()
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)

        try:
            git_user = GitUser.objects.get(tg_user=tg_user)
        except:
            git_user = GitUser(name="bob", email="bobin-email@lol.com", tg_user=tg_user)
            git_user.save()

        # Test when latest date should be NULL, promotion should happen
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(1, chat_member.rank)

        # Test again, no promotion should happen
        tg_user = TelegramUser(id=1337,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(fitz).date() -
                               datetime.timedelta(days=6))
        tg_user.save()
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        self.assertEqual(tg_user.latest_promotion_from_git_commit,
                         datetime.datetime.now(fitz).date() -
                         datetime.timedelta(days=6))
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(1, chat_member.rank)

        # Change latest promotion to 7 days ago, promotion should happen
        tg_user = TelegramUser(id=1337,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(fitz).date() -
                               datetime.timedelta(days=7))
        tg_user.save()
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(2, chat_member.rank)

        # Check that new random message dont mess up the user database
        update = MockUpdate()
        update.effective_user.id = 1337
        update.effective_message.text = "jepou juupeli juu"
        message_handler.handle_update(update)

        # Test again, no promotion
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(datetime.datetime.now(fitz).date(),
                         tg_user.latest_promotion_from_git_commit)
        self.assertEqual(2, chat_member.rank)

    def test_huutista(self):
        update = MockUpdate()
        update.effective_message.text = "Huutista"
        message_handler.handle_update(update=update)
        self.assertEqual("...joka tuutista! 😂", update.effective_message.reply_message_text)

    def test_huutista_should_not_trigger(self):
        update = MockUpdate()

        update.effective_message.text = "Huutista tälle"
        message_handler.handle_update(update=update)
        update.effective_message.text = "sinne huutista"
        message_handler.handle_update(update=update)

        self.assertEqual(update.effective_message.reply_message_text, None)

    def test_huutista_case_insensitive(self):
        update = MockUpdate()

        update.effective_message.text = "HUUTISTA"
        message_handler.handle_update(update=update)
        self.assertEqual("...joka tuutista! 😂", update.effective_message.reply_message_text)

        update.effective_message.text = "hUuTiStA"
        message_handler.handle_update(update=update)
        self.assertEqual("...joka tuutista! 😂", update.effective_message.reply_message_text)

        update.effective_message.text = "huutista"
        message_handler.handle_update(update=update)
        self.assertEqual("...joka tuutista! 😂", update.effective_message.reply_message_text)

    def test_db_updaters_command(self):
        update = MockUpdate()
        update.effective_message.text = "jepou juupeli juu"
        database.update_user_in_db(update)
        user = TelegramUser.objects.get(id="1337")
        self.assertEqual("bob", user.first_name)
        self.assertEqual("bobilainen", user.last_name)
        self.assertEqual("bob-bot", user.username)

    @mock.patch('os.getenv')
    @mock.patch('telegram.ext.Updater')
    def test_init_bot(self, mock_updater, mock_getenv):
        mock_updater.return_value = None
        mock_getenv.return_value = "DUMMY_ENV_VAR"
        with patch('bobweb.bob.main.Updater'):
            main.init_bot()

    async def test_backup_create(self):
        mock_bot = MockBot()
        global_admin = TelegramUser(id=1337)
        bob = Bob(id=1, global_admin=global_admin)
        bob.save()
        await db_backup.create(mock_bot)
        database_path = Path('bobweb/web/db.sqlite3')
        self.assertTrue(filecmp.cmp(database_path, mock_bot.sent_document.name, shallow=False))

    def test_ChatCommand_get_parameters(self):
        command = ChatCommand(name='test', regex=r'^[/.!]test_command($|\s)', help_text_short=('test', 'test'))
        expected = 'this is parameters \n asd'
        actual = command.get_parameters('/test_command   \n this is parameters \n asd')
        self.assertEqual(expected, actual)

        expected = ''
        actual = command.get_parameters('/test_command')
        self.assertEqual(expected, actual)

    def test_activity_state_no_implementation_nothing_happens(self):
        chat, user = init_chat_user()
        activity = ActivityState()
        activity.execute_state()
        processed = activity.preprocess_reply_data_hook('asd')
        activity.handle_response('asd')
        # Nothing has been returned and no messages have been sent to chat
        self.assertEqual('asd', processed)
        self.assertSequenceEqual([], chat.messages)

    def test_split_to_chunks_basic_cases(self):
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

    def test_flatten(self):
        list_of_lists = [[[[]]], [], [[]], [[], []]]
        self.assertEqual([], flatten(list_of_lists))

        list_of_lists_with_items = [[1], [2, 3], [4, [5, [6, [7, [8]]]]]]
        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8], flatten(list_of_lists_with_items))

        self.assertIsNone(flatten(None))  # If called with None, should return None
        self.assertEqual('abc', flatten('abc'))

    def test_min_max_normalize_simple_case_single_value(self):
        original_min, original_max = 0, 10
        original_value = 3

        new_min, new_max = 0, 1
        expected_values = Decimal('0.3')
        actual_value = min_max_normalize(original_value, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

    def test_min_max_normalize_simple_case_single_list(self):
        original_min, original_max = 0, 10
        original_values = [0, 1, 2, 3]

        new_min, new_max = 0, 25
        expected_values = [0, 2.5, 5, 7.5]
        actual_value = min_max_normalize(original_values, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

    def test_min_max_normalize_simple_case_list_of_lists(self):
        original_min, original_max = 0, 10
        original_values = [[0, 1], [2, 3]]

        new_min, new_max = 0, 5
        expected_values = [[0, 0.5], [1, 1.5]]
        actual_value = min_max_normalize(original_values, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

    def test_min_max_normalize_handles_scale_movement(self):
        original_min, original_max = 0, 10
        original_values = [0, 1, 2, 3]

        new_min, new_max = 50, 100
        expected_values = [50, 55, 60, 65]
        actual_value = min_max_normalize(original_values, original_min, original_max, new_min, new_max)
        self.assertEqual(expected_values, actual_value)

import filecmp
import os
import datetime
from pathlib import Path
from unittest import mock, IsolatedAsyncioTestCase
from unittest.mock import patch, Mock

from bobweb.bob.command import ChatCommand
from bobweb.bob.tests_mocks_v1 import MockUpdate, MockBot, MockUser, MockChat, MockMessage
from bobweb.bob.resources.bob_constants import fitz
from telegram.chat import Chat

from bobweb.bob import main

from bobweb.bob import db_backup
from bobweb.bob import git_promotions
from bobweb.bob import message_handler
from bobweb.bob import command_leet
from bobweb.bob import database

import django

from bobweb.bob.utils_common import weekday_count_between, next_weekday, prev_weekday, split_to_chunks, flatten

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

    def setUp(self) -> None:
        update = MockUpdate()
        update.effective_message.text = "jepou juupeli juu"
        update.effective_chat.id = 1337
        update.effective_user.id = 1337
        main.handle_update(update)
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
        main.handle_update(update=update)
        self.assertEqual(update.effective_message, None)

    def test_leet_command(self):
        update = MockUpdate()
        update.effective_message.text = "1337"
        up = u"\U0001F53C"
        down = u"\U0001F53D"

        member = ChatMember.objects.get(chat=update.effective_user.id, tg_user=update.effective_chat.id)
        member.rank = 0
        member.prestige = 0
        member.save()
        old_prestige = member.prestige
        with patch('bobweb.bob.command_leet.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 12, 37)
            main.handle_update(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.effective_message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 36)
            command_leet.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.effective_message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 37)
            command_leet.leet_command(update)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon alokas! 🔼 Lepo. ",
                             update.effective_message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            command_leet.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.effective_message.reply_message_text)

            for i in range(51):
                mock_datetime.datetime.now.return_value = datetime.datetime(1970 + i, 1, 1, 13, 37)
                command_leet.leet_command(update)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon pursimies! 🔼 Lepo. ",
                             update.effective_message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            for i in range(15):
                command_leet.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.effective_message.reply_message_text)
            self.assertEqual(old_prestige+1, ChatMember.objects.get(chat=update.effective_user.id,
                                                                    tg_user=update.effective_chat.id).prestige)
            self.assertEqual(0, ChatMember.objects.get(chat=update.effective_user.id,
                                                       tg_user=update.effective_chat.id).rank)

    def test_space_command(self):
        update = MockUpdate()
        update.effective_message.text = "/space"
        main.handle_update(update)
        self.assertRegex(update.effective_message.reply_message_text,
                         r"Seuraava.*\n.*Helsinki.*\n.*T-:")

    def test_time_command(self):
        update = MockUpdate()
        update.effective_message.text = "/aika"
        main.handle_update(update=update)
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
        main.handle_update(update)

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
        main.handle_update(update=update)
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

    def test_next_weekday(self):
        d = datetime.datetime
        self.assertEqual(d(2000, 1,  3), next_weekday(d(2000, 1, 1)))  # sat
        self.assertEqual(d(2000, 1,  3), next_weekday(d(2000, 1, 2)))  # sun
        self.assertEqual(d(2000, 1,  4), next_weekday(d(2000, 1, 3)))
        self.assertEqual(d(2000, 1,  5), next_weekday(d(2000, 1, 4)))
        self.assertEqual(d(2000, 1,  6), next_weekday(d(2000, 1, 5)))
        self.assertEqual(d(2000, 1,  7), next_weekday(d(2000, 1, 6)))
        self.assertEqual(d(2000, 1, 10), next_weekday(d(2000, 1, 7)))  # fri

    def test_prev_weekday(self):
        d = datetime.datetime
        self.assertEqual(d(1999, 12, 31), prev_weekday(d(2000, 1, 1)))  # sat
        self.assertEqual(d(1999, 12, 31), prev_weekday(d(2000, 1, 2)))  # sun
        self.assertEqual(d(1999, 12, 31), prev_weekday(d(2000, 1, 3)))
        self.assertEqual(d(2000,  1,  3), prev_weekday(d(2000, 1, 4)))
        self.assertEqual(d(2000,  1,  4), prev_weekday(d(2000, 1, 5)))
        self.assertEqual(d(2000,  1,  5), prev_weekday(d(2000, 1, 6)))
        self.assertEqual(d(2000,  1,  6), prev_weekday(d(2000, 1, 7)))  # fri

    def test_get_weekday_count_between_2_days(self):
        d = datetime.datetime
        between = weekday_count_between

        # 2022-01-01 is saturday
        self.assertEqual(0, between(d(2000, 1, 1), d(2000, 1, 1)))  # sat -> sat
        self.assertEqual(0, between(d(2000, 1, 1), d(2000, 1, 2)))  # sat -> sun
        # sat -> mon -  NOTE: as end date is not included, 0 week days
        self.assertEqual(0, between(d(2000, 1, 1), d(2000, 1, 3)))
        # sat -> tue - NOTE: monday is the only weekday in range
        self.assertEqual(1, between(d(2000, 1, 1), d(2000, 1, 4)))
        self.assertEqual(2, between(d(2000, 1, 1), d(2000, 1, 5)))
        self.assertEqual(3, between(d(2000, 1, 1), d(2000, 1, 6)))
        self.assertEqual(4, between(d(2000, 1, 1), d(2000, 1, 7)))
        self.assertEqual(5, between(d(2000, 1, 1), d(2000, 1, 8)))
        self.assertEqual(5, between(d(2000, 1, 1), d(2000, 1, 9)))
        self.assertEqual(5, between(d(2000, 1, 1), d(2000, 1, 10)))
        self.assertEqual(6, between(d(2000, 1, 1), d(2000, 1, 11)))

        # end date is not inclueded
        self.assertEqual(0, between(d(2000, 1, 3), d(2000, 1, 3)))
        self.assertEqual(1, between(d(2000, 1, 3), d(2000, 1, 4)))

        # order of dates does not matter
        self.assertEqual(6, between(d(2000, 1, 11), d(2000, 1, 1)))

        # Note, year cannot have less than 260 week days or more than 262
        # 366 day year starting on saturday will end on saturday.
        # More info https://en.wikipedia.org/wiki/Common_year_starting_on_Saturday
        self.assertEqual(260, between(d(2000, 1, 1), d(2001, 1, 1)))  # 365 days. 53 saturdays and sundays
        self.assertEqual(261, between(d(2001, 1, 1), d(2002, 1, 1)))  # 365 days, 52 saturdays and sundays
        self.assertEqual(262, between(d(2004, 1, 1), d(2005, 1, 1)))  # 366 days, 52 saturdays and sundays

import filecmp
import os
import sys
import datetime
from unittest import mock, IsolatedAsyncioTestCase
from unittest.mock import patch

from bobweb.bob.command import ChatCommand
from bobweb.bob.utils_test import always_last_choice, MockUpdate, MockBot, MockEntity, MockUser, MockChat, MockMessage
from bobweb.bob.resources.bob_constants import DEFAULT_TIMEZONE
from telegram.chat import Chat

from bobweb.bob import main
import pytz

from bobweb.bob import db_backup
from bobweb.bob import git_promotions
from bobweb.bob import message_handler
from bobweb.bob import command_kuulutus
from bobweb.bob import command_leet
from bobweb.bob import database

import django
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
        update.message.text = "jepou juupeli juu"
        update.effective_chat.id = 1337
        update.effective_user.id = 1337
        main.message_handler(update)
        main.broadcast_and_promote(update)

    def test_reply_handler(self):
        update = MockUpdate()
        mock_chat = MockChat()
        mock_message = MockMessage(mock_chat.chat)
        mock_message.from_user = MockUser()
        mock_message.text = "Git käyttäjä bla bla blaa"
        mock_message.reply_to_message = mock_message
        update.message = mock_message
        admin = TelegramUser(id=1337)
        bob = Bob(id=1, global_admin=admin)
        bob.save()

    def test_process_entity(self):
        message_entity = MockEntity()
        message_entity.type = "mention"

        mock_update = MockUpdate()
        mock_update.message.text = "@bob-bot "
        git_promotions.process_entity(message_entity, mock_update)

        mock_update = MockUpdate()
        mock_update.message.text = "@bob-bot"
        git_promotions.process_entity(message_entity, mock_update)

    def test_empty_incoming_message(self):
        update = MockUpdate()
        update.message = None
        main.message_handler(update=update)
        self.assertEqual(update.message, None)

    def test_leet_command(self):
        update = MockUpdate()
        update.message.text = "1337"
        up = u"\U0001F53C"
        down = u"\U0001F53D"

        member = ChatMember.objects.get(chat=update.effective_user.id, tg_user=update.effective_chat.id)
        member.rank = 0
        member.prestige = 0
        member.save()
        old_prestige = member.prestige
        with patch('bobweb.bob.command_leet.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 12, 37)
            main.message_handler(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 36)
            command_leet.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 37)
            command_leet.leet_command(update)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon alokas! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            command_leet.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            for i in range(51):
                mock_datetime.datetime.now.return_value = datetime.datetime(1970 + i, 1, 1, 13, 37)
                command_leet.leet_command(update)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon pursimies! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            for i in range(15):
                command_leet.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)
            self.assertEqual(old_prestige+1, ChatMember.objects.get(chat=update.effective_user.id,
                                                                    tg_user=update.effective_chat.id).prestige)
            self.assertEqual(0, ChatMember.objects.get(chat=update.effective_user.id,
                                                       tg_user=update.effective_chat.id).rank)

    def test_space_command(self):
        update = MockUpdate()
        update.message.text = "/space"
        main.message_handler(update)
        self.assertRegex(update.message.reply_message_text,
                         r"Seuraava.*\n.*Helsinki.*\n.*T-:")

    def test_time_command(self):
        update = MockUpdate()
        update.message.text = "/aika"
        main.message_handler(update=update)
        hours_now = str(datetime.datetime.now(pytz.timezone(DEFAULT_TIMEZONE)).strftime('%H'))
        hours_regex = r"\b" + hours_now + r":"
        self.assertRegex(update.message.reply_message_text,
                        hours_regex)

    def test_low_probability_reply(self):
        update = MockUpdate()
        update.message.text = "Anything"
        update.message.reply_message_text = None
        message_handler.message_handler(update=update)
        try:
            self.assertEqual(None, update.message.reply_message_text)
        except AssertionError:
            self.assertEqual("Vaikuttaa siltä että olette todella onnekas " + "\U0001F340",
                             update.message.reply_message_text)

        random_int = 1
        message_handler.low_probability_reply(update=update, integer=random_int)
        self.assertEqual("Vaikuttaa siltä että olette todella onnekas " + "\U0001F340",
                         update.message.reply_message_text)

        random_int = 2
        message_handler.low_probability_reply(update=update, integer=random_int)
        self.assertTrue(True)
        message_handler.low_probability_reply(update=update, integer=0)

    def test_broadcast_and_promote(self):
        update = MockUpdate()
        main.broadcast_and_promote(update)
        self.assertTrue(True)

    def test_promote_committer_or_find_out_who_he_is(self):
        update = MockUpdate()
        os.environ["COMMIT_AUTHOR_NAME"] = "bob"
        os.environ["COMMIT_AUTHOR_NAME"] = "bob@bob.com"
        git_promotions.promote_committer_or_find_out_who_he_is(update)
        self.assertTrue(True)

    def test_get_git_user_and_commit_info(self):
        git_promotions.get_git_user_and_commit_info()
        self.assertTrue(True)

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
                               datetime.datetime.now(pytz.timezone(DEFAULT_TIMEZONE)).date() -
                               datetime.timedelta(days=6))
        tg_user.save()
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        self.assertEqual(tg_user.latest_promotion_from_git_commit,
                         datetime.datetime.now(pytz.timezone(DEFAULT_TIMEZONE)).date() -
                         datetime.timedelta(days=6))
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(1, chat_member.rank)

        # Change latest promotion to 7 days ago, promotion should happen
        tg_user = TelegramUser(id=1337,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(pytz.timezone(DEFAULT_TIMEZONE)).date() -
                               datetime.timedelta(days=7))
        tg_user.save()
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(2, chat_member.rank)

        # Check that new random message dont mess up the user database
        update = MockUpdate()
        update.effective_user.id = 1337
        update.message.text = "jepou juupeli juu"
        main.message_handler(update)

        # Test again, no promotion
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(datetime.datetime.now(pytz.timezone(DEFAULT_TIMEZONE)).date(),
                         tg_user.latest_promotion_from_git_commit)
        self.assertEqual(2, chat_member.rank)

    def test_huutista(self):
        update = MockUpdate()
        update.message.text = "Huutista"
        main.message_handler(update=update)
        self.assertEqual("...joka tuutista! 😂", update.message.reply_message_text)

    def test_huutista_should_not_trigger(self):
        update = MockUpdate()

        update.message.text = "Huutista tälle"
        message_handler.message_handler(update=update)
        update.message.text = "sinne huutista"
        message_handler.message_handler(update=update)

        self.assertEqual(update.message.reply_message_text, None)

    def test_huutista_case_insensitive(self):
        update = MockUpdate()

        update.message.text = "HUUTISTA"
        message_handler.message_handler(update=update)
        self.assertEqual("...joka tuutista! 😂", update.message.reply_message_text)

        update.message.text = "hUuTiStA"
        message_handler.message_handler(update=update)
        self.assertEqual("...joka tuutista! 😂", update.message.reply_message_text)

        update.message.text = "huutista"
        message_handler.message_handler(update=update)
        self.assertEqual("...joka tuutista! 😂", update.message.reply_message_text)

    def test_db_updaters_command(self):
        update = MockUpdate()
        update.message.text = "jepou juupeli juu"
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
        self.assertTrue(filecmp.cmp('bobweb/web/db.sqlite3', mock_bot.sent_document.name, shallow=False))

    def test_ChatCommand_get_parameters(self):
        command = ChatCommand(name='test', regex=r'^[/.!]test_command($|\s)', help_text_short=('test', 'test'))
        expected = 'this is parameters \n asd'
        actual = command.get_parameters('/test_command   \n this is parameters \n asd')
        self.assertEqual(expected, actual)

        expected = ''
        actual = command.get_parameters('/test_command')
        self.assertEqual(expected, actual)




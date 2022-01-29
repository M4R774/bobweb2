import os
import re
import sys
import time
import datetime
from unittest import TestCase, mock
from unittest.mock import patch

import pytz

import main
import pytz

sys.path.append('../web')  # needed for sibling import
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
from django.conf import settings
django.setup()
from bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser


class Test(TestCase):
    def setUp(self) -> None:
        main.ranks = []
        main.read_ranks_file()
        update = MockUpdate()
        update.message.text = "jepou juupeli juu"
        update.effective_chat.id = 1337
        update.effective_user.id = 1337
        main.message_handler(update, context=None)
        main.broadcast_and_promote(update)

    def test_reply_handler(self):
        update = MockUpdate()
        mock_message = MockMessage()
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
        main.process_entity(message_entity, mock_update)

        mock_update = MockUpdate()
        mock_update.message.text = "@bob-bot"
        main.process_entity(message_entity, mock_update)

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
        with patch('main.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 12, 37)
            main.message_handler(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 36)
            main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 37)
            main.leet_command(update, None)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon alokas! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            for i in range(51):
                mock_datetime.datetime.now.return_value = datetime.datetime(1970 + i, 1, 1, 13, 37)
                main.leet_command(update, None)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon pursimies! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            for i in range(15):
                main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)
            self.assertEqual(old_prestige+1, ChatMember.objects.get(chat=update.effective_user.id,
                                                                    tg_user=update.effective_chat.id).prestige)
            self.assertEqual(0, ChatMember.objects.get(chat=update.effective_user.id,
                                                       tg_user=update.effective_chat.id).rank)

    def test_space_command(self):
        update = MockUpdate()
        update.message.text = "/space"
        main.message_handler(update, None)
        self.assertRegex(update.message.reply_message_text,
                         r"Seuraava.*\n.*Helsinki.*\n.*T-:")

    def test_users_command(self):
        update = MockUpdate()
        update.message.text = "/users"
        main.message_handler(update=update, context=None)
        self.assertNotEqual(None, update.message.reply_message_text)

    def test_broadcast_toggle_command(self):
        update = MockUpdate()

        update.message.text = "/kuulutus On"
        main.message_handler(update=MockUpdate, context=None)
        self.assertEqual("Kuulutukset ovat nyt päällä tässä ryhmässä.",
                         update.message.reply_message_text)

        update.message.text = "/kuulutus hölynpöly"
        main.broadcast_toggle_command(update=MockUpdate, context=None)
        self.assertEqual("Tällä hetkellä kuulutukset ovat päällä.",
                         update.message.reply_message_text)

        update.message.text = "/Kuulutus oFf"
        main.broadcast_toggle_command(update=MockUpdate, context=None)
        self.assertEqual("Kuulutukset ovat nyt pois päältä.",
                         update.message.reply_message_text)

        update.message.text = "/kuulutuS juupeli juu"
        main.broadcast_toggle_command(update=MockUpdate, context=None)
        self.assertEqual("Tällä hetkellä kuulutukset ovat pois päältä.",
                         update.message.reply_message_text)

    def test_broadcast_command(self):
        update = MockUpdate()
        main.broadcast_command(update, None)
        self.assertTrue(True)
    
    def test_time_command(self):
        update = MockUpdate()
        update.message.text = "/time"
        main.message_handler(update=MockUpdate, context=None)
        hours_now = str(datetime.datetime.now(pytz.timezone('Europe/Helsinki')).strftime('%H'))
        hours_regex = r"\b" + hours_now + r":"
        self.assertRegex(update.message.reply_message_text,
                        hours_regex)

    def test_broadcast_and_promote(self):
        update = MockUpdate()
        main.broadcast_and_promote(update)
        self.assertTrue(True)

    def test_promote_committer_or_find_out_who_he_is(self):
        update = MockUpdate()
        main.promote_committer_or_find_out_who_he_is(update)
        self.assertTrue(True)

    def test_get_git_user_and_commit_info(self):
        main.get_git_user_and_commit_info()
        self.assertTrue(True)

    def test_promote_or_praise(self):
        tg_user = TelegramUser(id=1337,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(pytz.timezone('Europe/Helsinki')).date() -
                               datetime.timedelta(days=8))
        git_user = GitUser(tg_user=tg_user)
        mock_bot = MockBot()
        main.promote_or_praise(git_user, mock_bot)
        self.assertTrue(True)

    def test_db_updaters_command(self):
        update = MockUpdate()
        update.message.text = "jepou juupeli juu"
        main.message_handler(update, context=None)
        self.assertTrue(True)

    def test_init_bot(self):
        main.init_bot()
        self.assertTrue(True)


class MockUser:
    id = 1337
    first_name = "bob"
    last_name = "bobilainen"
    username = "bob-bot"
    is_bot = True

    def mention_markdown_v2(self):
        return "hello world!"


class MockChat:
    id = 1337


class MockEntity:
    type = ""


class MockBot:
    def sendMessage(self, chat, message):
        print(chat, message)


class MockMessage:
    text = "/users"
    reply_message_text = None
    reply_to_message = None
    from_user = None
    bot = MockBot()

    def reply_text(self, message, quote=None):
        self.reply_message_text = message
        print(message)

    def reply_markdown_v2(self, message, reply_markup):
        self.reply_message_text = message
        print(message)


class MockUpdate:
    bot = MockBot()
    effective_user = MockUser()
    effective_chat = MockChat()
    message = MockMessage()

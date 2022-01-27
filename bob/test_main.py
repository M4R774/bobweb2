import os
import re
import sys
import time
from datetime import datetime, date
from unittest import TestCase, mock
from unittest.mock import patch

import main

sys.path.append('../web')  # needed for sibling import
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
from django.conf import settings
django.setup()
from bobapp.models import Chat, TelegramUser, ChatMember, Bob


class Test(TestCase):
    def setUp(self) -> None:
        main.ranks = []
        main.read_ranks_file()
        update = MockUpdate
        update.message.text = "jepou juupeli juu"
        update.effective_chat.id = 1337
        update.effective_user.id = 1337
        main.message_handler(update, context=None)

    def test_init_bot(self):
        main.init_bot()
        self.assertTrue(True)

    def test_leet_command(self):
        update = MockUpdate
        update.message.text = "1337"
        up = u"\U0001F53C"
        down = u"\U0001F53D"

        member = ChatMember.objects.get(chat=update.effective_user.id, tg_user=update.effective_chat.id)
        member.rank = 0
        member.prestige = 0
        member.save()
        old_prestige = member.prestige
        with patch('main.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(1970, 1, 1, 12, 37)
            main.message_handler(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.now.return_value = datetime(1970, 1, 1, 13, 36)
            main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.now.return_value = datetime(1970, 1, 1, 13, 37)
            main.leet_command(update, None)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon alokas! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.now.return_value = datetime(1970, 1, 1, 13, 38)
            main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            for i in range(51):
                mock_datetime.now.return_value = datetime(1970 + i, 1, 1, 13, 37)
                main.leet_command(update, None)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon pursimies! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.now.return_value = datetime(1970, 1, 1, 13, 38)
            for i in range(52):
                main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)
            self.assertEqual(old_prestige+1, ChatMember.objects.get(chat=update.effective_user.id,
                                                                    tg_user=update.effective_chat.id).prestige)
            self.assertEqual(0, ChatMember.objects.get(chat=update.effective_user.id,
                                                       tg_user=update.effective_chat.id).rank)

    def test_space_command(self):
        update = MockUpdate
        update.message.text = "/space"
        main.message_handler(update, None)
        self.assertRegex(update.message.reply_message_text,
                         r"Seuraava.*\n.*Helsinki.*\n.*T-:")

    def test_users_command(self):
        update = MockUpdate
        update.message.text = "/users"
        main.message_handler(update=MockUpdate, context=None)
        self.assertNotEqual(None, update.message.reply_message_text)

    def test_broadcast_toggle_command(self):
        update = MockUpdate

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
        update = MockUpdate
        main.broadcast_command(update, None)
        self.assertTrue(True)

    def test_db_updaters_command(self):
        update = MockUpdate
        update.message.text = "jepou juupeli juu"
        main.message_handler(update, context=None)
        self.assertTrue(True)


class MockUser:
    id = 1337
    first_name = "bob"
    last_name = "bobilainen"
    username = "bob-bot"

    def mention_markdown_v2(self):
        return "hello world!"


class MockChat:
    id = 1337


class MockMessage:
    text = "/users"
    reply_message_text = None

    def reply_text(self, message, quote=None):
        self.reply_message_text = message
        print(message)

    def reply_markdown_v2(self, message, reply_markup):
        self.reply_message_text = message
        print(message)


class MockBot():
    def sendMessage(self, chat, message):
        print(chat, message)


class MockUpdate:
    bot = MockBot()
    effective_user = MockUser()
    effective_chat = MockChat()
    message = MockMessage()

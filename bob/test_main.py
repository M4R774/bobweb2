import os
import re
import sys
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import patch

import main


class Test(TestCase):
    def setUp(self) -> None:
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
        with patch('main.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(1970, 1, 1, 12, 37)
            main.leet_command(update, None)
            self.assertEqual("Ei kello ole 13:37...", update.message.reply_message_text)

            mock_datetime.now.return_value = datetime(1970, 1, 1, 13, 36)
            main.leet_command(update, None)
            self.assertEqual("Ei kello ole 13:37...", update.message.reply_message_text)

            mock_datetime.now.return_value = datetime(1970, 1, 1, 13, 37)
            main.leet_command(update, None)
            self.assertEqual("Jee!", update.message.reply_message_text)

            mock_datetime.now.return_value = datetime(1970, 1, 1, 13, 38)
            main.leet_command(update, None)
            self.assertEqual("Ei kello ole 13:37...", update.message.reply_message_text)

    def test_space_command(self):
        update = MockUpdate
        main.space_command(update, None)
        self.assertRegex(update.message.reply_message_text,
                         r"Seuraava.*\n.*Helsinki.*\n.*T-:")

    def test_users_command(self):
        update = MockUpdate
        main.users_command(update=MockUpdate, context=None)
        self.assertNotEqual(None, update.message.reply_message_text)

    def test_broadcast_toggle_command(self):
        update = MockUpdate

        update.message.text = "/kuulutus On"
        main.broadcast_toggle_command(update=MockUpdate, context=None)
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

    def test_broadcast(self):
        main.broadcast(None, None)
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


class MockUpdate:
    effective_user = MockUser()
    effective_chat = MockChat()
    message = MockMessage()

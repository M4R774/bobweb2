import os
import sys
from unittest import TestCase
import main


class Test(TestCase):
    def setUp(self) -> None:
        pass

    def test_init_bot(self):
        main.init_bot()
        self.assertTrue(True)

    def test_start(self):
        main.start(update=MockUpdate, context=None)
        self.assertTrue(True)

    def test_echo(self):
        main.echo(update=MockUpdate, context=None)
        self.assertTrue(True)

    def test_help_command(self):
        main.help_command(update=MockUpdate, context=None)
        self.assertTrue(True)
    
    def test_space_command(self):
        main.space_command(update=MockUpdate, context=None)
        self.assertTrue(True)

    def test_users_command(self):
        main.users_command(update=MockUpdate, context=None)
        self.assertTrue(True)

    def test_db_updaters_command(self):
        main.message_handler(update=MockUpdate, context=None)
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


    def reply_text(self, message):
        print(message)

    def reply_markdown_v2(self, message, reply_markup):
        pass


class MockUpdate:
    effective_user = MockUser()
    effective_chat = MockChat()
    message = MockMessage()

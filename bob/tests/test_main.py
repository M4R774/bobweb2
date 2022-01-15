from unittest import TestCase

from bob import main


class Test(TestCase):
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


class MockUser:
    def mention_markdown_v2(self):
        return "hello world"


class MockMessage:
    text = ""

    def reply_text(self, message):
        print(message)

    def reply_markdown_v2(self, message, reply_markup):
        pass


class MockUpdate:
    effective_user = MockUser()
    message = MockMessage()

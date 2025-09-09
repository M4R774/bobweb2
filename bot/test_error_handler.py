from types import TracebackType, FrameType
from unittest import mock

import django.test
import pytest
from asynctest import Mock
from django.core import management
from telegram.ext import CallbackContext

from bot import main, database
from bot.error_handler import unhandled_bot_exception_handler
from bot.tests_mocks_v2 import init_chat_user, MockUpdate, MockMessage, MockChat, MockUser


@pytest.mark.asyncio
class ErrorHandlerTest(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(ErrorHandlerTest, cls).setUpClass()
        management.call_command('migrate')

    @mock.patch('random.choice', lambda collection: collection[0])  # Fix random emoji choice to be the first
    async def test_error_handler_responses_to_message_that_caused_the_error(self):
        # Create a mock update and mock context with information about an error
        chat, user = init_chat_user()

        update = MockUpdate(message=MockMessage(chat, user))
        context = Mock(spec=CallbackContext)
        context.bot = chat.bot

        # Here we use a hack to create a "real" exception by raising it and then catching it
        try:
            raise Exception('Test exception')  # NOSONAR
        except Exception as e:
            context.error = e

        # Call the error handler
        with self.assertLogs(level='ERROR') as log:
            await unhandled_bot_exception_handler(update, context)
            self.assertIn('error:bot.error_handler:Exception while handling an update', log.output[-1])
            self.assertIn('Virhe 🚧 Asiasta ilmoitettu ylläpidolle tunnisteella 😀😀😀', chat.last_bot_txt())

        # Now if we create another chat, persist it to database and set it as the error log, all errors are sent to it
        # by the bot. For the new chat we use the same bot so that it can send the error to another chat
        error_chat = MockChat(bot=chat.bot)  # New chat with the same bot
        admin_user = MockUser(chat=error_chat)  # New user
        await admin_user.send_message('This is error log chat')  # Send a single message to persist the chat
        bot_config = database.get_bot()
        bot_config.error_log_chat = database.get_chat(chat_id=error_chat.id)
        bot_config.save()

        # When we trigger the error again, it should be sent to the error log chat
        # self.assertEqual([], error_chat.messages)
        await unhandled_bot_exception_handler(update, context)
        self.assertIn('An exception was raised while handling an update (user given emoji id=😀😀😀)',
                      error_chat.messages[-1].message)  # Last message in the error log chat
        self.assertIn('Exception: Test exception', error_chat.messages[-1].message)




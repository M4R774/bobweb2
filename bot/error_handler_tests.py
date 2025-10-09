from unittest import mock

import django.test
import pytest
from asynctest import Mock
from telegram.ext import CallbackContext

from bot import main, database, command_service
from bot.error_handler import unhandled_bot_exception_handler, deny_button, allow_button
from bot.tests_mocks_v2 import init_chat_user, MockUpdate, MockMessage, MockChat, MockUser, assert_buttons_equals
from bot.tests_constants import MockTestException


@pytest.mark.asyncio
class ErrorHandlerTest(django.test.TransactionTestCase):

    @mock.patch('random.choice', lambda collection: collection[0])  # Fix random emoji choice to be the first
    async def test_error_handler_when_no_error_log_chat(self):
        # Create a mock update and mock context with information about an error
        chat, user = init_chat_user()
        user.username = 'testuser123'

        update = MockUpdate(message=MockMessage(chat, user))
        context = Mock(spec=CallbackContext)
        context.bot = chat.bot

        # Here we use a hack to create a "real" exception by raising it and then catching it
        try:
            raise MockTestException('Test exception')  # NOSONAR
        except MockTestException as e:
            context.error = e

        # Call the error handler
        with self.assertLogs(level='ERROR') as log:
            await unhandled_bot_exception_handler(update, context)
            self.assertIn('error:bot.error_handler:Exception while handling an update', log.output[-1])

        # Check that there are no messages from bot in the chat
        self.assertEqual(0, len(chat.bot.messages))


    @mock.patch('random.choice', lambda collection: collection[0])  # Fix random emoji choice to be the first
    async def test_error_handler_responses_to_message_that_caused_the_error(self):
        chat, user, error_chat = await self.setup_test_case_chats_and_users_and_call_error_handler()

        # The chat where the error was triggered should have a notification about it
        self.assertIn('Virhe 🚧 tunnisteella 😀😀😀', chat.last_bot_txt())

        # Also error log should have a message with stack trace about it
        error_report_text = error_chat.last_bot_txt()
        self.assertIn('An exception was raised while handling an update (user given emoji id=😀😀😀)',
                      error_report_text)  # Last message in the error log chat
        self.assertIn('Exception: Test exception', error_report_text)

        # Check that the users username is NOT in any text sent from bot
        all_error_chat_messages = error_chat.messages
        for msg in all_error_chat_messages:
            self.assertNotIn(user.username, msg.text)

        await user.press_button(deny_button)  # Press deny button to clear the activity


    @mock.patch('random.choice', lambda collection: collection[0])  # Fix random emoji choice to be the first
    async def test_error_handler_user_accepts_sharing_error_details(self):
        chat, user, error_chat = await self.setup_test_case_chats_and_users_and_call_error_handler()

        self.assertIn('Sallitko seuraavien tietojen jakamisen ylläpidolle?', chat.last_bot_txt())
        assert_buttons_equals(self, [deny_button, allow_button], chat.last_bot_msg().reply_markup)

        # Check that the users username is NOT in any text sent from bot
        all_error_chat_messages = error_chat.messages
        for msg in all_error_chat_messages:
            self.assertNotIn(user.username, msg.text)

        # Check that the chat activity exists
        all_activities = command_service.instance.current_activities
        self.assertEqual(1, len(all_activities))
        error_confirmation_activity = all_activities[0]
        self.assertEqual('ErrorSharingPermissionState', error_confirmation_activity.state.__class__.__name__)

        await user.press_button(allow_button)
        self.assertIn('Kiitoksia! Virhe 😀😀😀 toimitettu tarkempine tietoineen ylläpidolle', chat.last_bot_txt())

        # Ensure there is no activity anymore
        self.assertEqual(0, len(command_service.instance.current_activities))

        # Check that the error details have been sent to the error log chat
        error_report_msg = error_chat.last_bot_msg()
        # Should be a reply to the traceback message
        self.assertEqual(error_chat.messages[-2], error_report_msg.reply_to_message)

        self.assertIn('Error details shared by user (😀😀😀):', error_report_msg.text)
        self.assertIn('&quot;username&quot;: &quot;' + user.username + '&quot;', error_report_msg.text)


    @mock.patch('random.choice', lambda collection: collection[0])  # Fix random emoji choice to be the first
    async def test_error_handler_user_rejects_sharing_error_details(self):
        chat, user, error_chat = await self.setup_test_case_chats_and_users_and_call_error_handler()

        self.assertIn('Sallitko seuraavien tietojen jakamisen ylläpidolle?', chat.last_bot_txt())
        assert_buttons_equals(self, [deny_button, allow_button], chat.last_bot_msg().reply_markup)

        # Check that the users username is NOT in any text sent from bot
        all_error_chat_messages = error_chat.messages
        for msg in all_error_chat_messages:
            self.assertNotIn(user.username, msg.text)

        # Check that the chat activity exists
        all_activities = command_service.instance.current_activities
        self.assertEqual(1, len(all_activities))
        error_confirmation_activity = all_activities[0]
        self.assertEqual('ErrorSharingPermissionState', error_confirmation_activity.state.__class__.__name__)

        await user.press_button(deny_button)
        self.assertIn('Asia selvä! Virheen 😀😀😀 tiedot poistettu', chat.last_bot_txt())

        # Ensure there is no activity anymore
        self.assertEqual(0, len(command_service.instance.current_activities))

        # Check that the error details have not been sent to the error log chat
        # Should only contain two messages. Initial message and the stacktrace message
        self.assertEqual(2, len(error_chat.messages))
        self.assertIn('An exception was raised while handling an update', error_chat.last_bot_txt())

        # Check that the users username is NOT in any text sent from bot
        all_error_chat_messages = error_chat.messages
        for msg in all_error_chat_messages:
            self.assertNotIn(user.username, msg.text)

    async def setup_test_case_chats_and_users_and_call_error_handler(self) -> tuple[MockChat, MockUser, MockChat]:
        """ Creates base state for other tests where error is caused in chat by a message from user. """
        chat, user = init_chat_user()
        user.username = 'testuser123'
        await user.send_message('hi')

        # Chat where error occurs
        update = MockUpdate(message=MockMessage(chat, user, text='This message will cause an error'))
        context = Mock(spec=CallbackContext)
        context.bot = chat.bot

        # Error log chat where error reports are sent
        error_chat = MockChat(bot=chat.bot)  # New chat with the same bot
        admin_user = MockUser(chat=error_chat)  # New user
        await admin_user.send_message('This is error log chat')  # Send a single message to persist the chat
        bot_config = database.get_bot()
        bot_config.error_log_chat = database.get_chat(chat_id=error_chat.id)
        bot_config.save()

        try:
            raise MockTestException('Test exception')  # NOSONAR
        except MockTestException as e:
            context.error = e

        # Call the error handler
        with self.assertLogs(level='ERROR') as log:
            await unhandled_bot_exception_handler(update, context)
            self.assertIn('error:bot.error_handler:Exception while handling an update', log.output[-1])
        return chat, user, error_chat

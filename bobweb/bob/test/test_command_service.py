from unittest import mock
from unittest.mock import Mock

import django
import pytest
from django.core import management
from django.test import TestCase

import bobweb.bob.command_service
from bobweb.bob import command_service, database
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.main import main
from bobweb.bob.tests_mocks_v2 import init_chat_user, assert_buttons_equals, MockUpdate
from bobweb.web.bobapp.models import Bob


@pytest.mark.asyncio
class CommandServiceTest(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(CommandServiceTest, cls).setUpClass()
        management.call_command('migrate')

    async def test_reply_and_callback_query_handler_should_delegate_button_press(self):
        # First star an activity, then press button and check that the handler was called and the message updated
        chat, user = init_chat_user()
        await user.send_message('/kysymys')

        self.assertIn('Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille. '
                      'Aloita luomalla kysymyskausi alla olevalla toiminnolla.', chat.last_bot_txt())
        assert_buttons_equals(self, ['Info ⁉', 'Aloita kausi 🚀', 'Tilastot 📊'], chat.last_bot_msg())

        # Create mock object with same functionality as the original just to assert that it was called once
        with mock.patch(
                'bobweb.bob.command_service.instance.reply_and_callback_query_handler',
                wraps=bobweb.bob.command_service.instance.reply_and_callback_query_handler) as mock_method:
            await user.press_button_with_text('Tilastot 📊')

            # Should have been called once and the message should have updated
            mock_method.assert_called_once()
            self.assertIn('Ei lainkaan kysymyskausia.', chat.last_bot_txt())

    async def test_reply_and_callback_query_handler_should_inform_if_activity_has_been_timeouted(self):
        # Tests that the message is updated with information if the activity has been timed outed when
        # user clicks/taps on any button in the inline keyboard
        command_service.instance.current_activities.clear()
        chat, user = init_chat_user()
        await user.send_message('/kysymys')

        self.assertIn('Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille. '
                      'Aloita luomalla kysymyskausi alla olevalla toiminnolla.', chat.last_bot_txt())
        assert_buttons_equals(self, ['Info ⁉', 'Aloita kausi 🚀', 'Tilastot 📊'], chat.last_bot_msg())

        # Now we remove the activity from the command service
        self.assertEqual(1, len(command_service.instance.current_activities))
        command_service.instance.current_activities.clear()
        self.assertEqual(0, len(command_service.instance.current_activities))

        # If user tries to press any button in the message, it is updated and the buttons are removed
        with mock.patch(
                'bobweb.bob.command_service.instance.reply_and_callback_query_handler',
                wraps=bobweb.bob.command_service.instance.reply_and_callback_query_handler) as mock_method:
            await user.press_button_with_text('Tilastot 📊')
            mock_method.assert_called_once()

            # Message should now have updated information that the activity has been timed out
            self.assertIn('Toimenpide aikakatkaistu ⌛', chat.last_bot_txt())

            # There should not be any buttons anymore
            assert_buttons_equals(self, [], chat.last_user_msg())

    async def test_starting_new_activity_without_host_message_logs_error_to_specified_error_log_chat(self):
        """ If new activity is started, and somehow it is missing a host message, information about this is both
            logged to the stdout and by bot sending a message to the error chat if that is specified. """
        command_service.instance.current_activities.clear()
        chat, user = init_chat_user()
        await user.send_message('test')

        context = Mock()
        context.bot = chat.bot

        bot_from_db: Bob = database.get_the_bob()
        bot_from_db.error_log_chat = database.get_chat(chat_id=chat.id)
        bot_from_db.save()

        with self.assertLogs(level='WARNING') as log:
            await command_service.instance.start_new_activity(
                initial_update=MockUpdate(),
                context=context,
                initial_state=ActivityState())
            expected_log = ("Started new CommandActivity for which its initial state did not create a host message. "
                            "InitialState: <class 'bobweb.bob.activities.activity_state.ActivityState'>")
            self.assertIn(expected_log, log.output[-1])

            self.assertEqual(0, len(command_service.instance.current_activities))
            # Same log message has been sent to the error chat by the bot
            self.assertEqual(expected_log, chat.last_bot_txt())

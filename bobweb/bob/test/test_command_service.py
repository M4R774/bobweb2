from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase

import bobweb.bob.command_service
from bobweb.bob import command_service
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.tests_mocks_v2 import init_chat_user, assert_buttons_equals, MockUpdate


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

    async def test_command_activity_without_host_message_is_logged_and_removed(self):
        """ If by any chance a command activity is created and added to the CommandService without host message,
            this should be logged and the message removed from the command services active activities list.
            No confirmation on how this happens, however "Bug fixes (#263)"-commit (12.1.2024) introduced a new bug
            "TypeError: Object of type CommandActivity is not JSON serializable" when json.dump() was given a
            CommandActivity as parameter. So in addition this verifies that that does not happen anymore. """
        # First add new activity without host message to the services activities list
        command_service.instance.current_activities.clear()
        activity_without_host_message = CommandActivity(initial_update=None, host_message=None)
        command_service.instance.current_activities.append(activity_without_host_message)

        self.assertEqual(1, len(command_service.instance.current_activities))

        # Create message that is reply to another message and process it with reply_and_callback_query_handler
        chat, user = init_chat_user()
        message = await user.send_message('test1')
        reply_message = await user.send_message('test2', reply_to_message=message)
        mock_update = MockUpdate(message=reply_message)
        await command_service.instance.reply_and_callback_query_handler(mock_update)

        # Now the problematic activity has been removed
        self.assertEqual(0, len(command_service.instance.current_activities))

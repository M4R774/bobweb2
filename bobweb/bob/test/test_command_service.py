from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase

import bobweb.bob.command_service
from bobweb.bob import command_service
from bobweb.bob.tests_mocks_v2 import init_chat_user, assert_buttons_equals


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


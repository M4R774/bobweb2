from unittest import mock
from unittest.mock import AsyncMock

import django
import pytest
from django.core import management
from django.test import TestCase

import bobweb.bob.command_service
from bobweb.bob import command_service
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_msg_btn_utils import button_labels_from_reply_markup


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

        self.assertIn('Valitse toiminto alapuolelta', chat.last_bot_txt())
        expected_buttons = ['Info ⁉', 'Kausi 📅', 'Tilastot 📊']
        actual_buttons = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
        self.assertEqual(expected_buttons, actual_buttons)

        # Create mock object with same functionality as the original just to assert that it was called once
        with mock.patch(
                'bobweb.bob.command_service.instance.reply_and_callback_query_handler',
                wraps=bobweb.bob.command_service.instance.reply_and_callback_query_handler) as mock_method:
            await user.press_button_with_text('Tilastot')

            # Should have been called once and the message should have updated
            mock_method.assert_called_once()
            self.assertIn('Ei lainkaan kysymyskausia.', chat.last_bot_txt())

    async def test_reply_and_callback_query_handler_should_inform_if_activity_has_been_timeouted(self):
        # Tests that the message is updated with information if the activity has been timed outed when
        # user clicks/taps on any button in the inline keyboard
        chat, user = init_chat_user()
        await user.send_message('/kysymys')

        self.assertIn('Valitse toiminto alapuolelta', chat.last_bot_txt())
        expected_buttons = ['Info ⁉', 'Kausi 📅', 'Tilastot 📊']
        actual_buttons = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
        self.assertEqual(expected_buttons, actual_buttons)

        # Now we remove the activity from the command service
        self.assertEqual(1, len(command_service.instance.current_activities))
        command_service.instance.current_activities.clear()
        self.assertEqual(0, len(command_service.instance.current_activities))

        # If user tries to press any button in the message, it is updated and the buttons are removed
        with mock.patch(
                'bobweb.bob.command_service.instance.reply_and_callback_query_handler',
                wraps=bobweb.bob.command_service.instance.reply_and_callback_query_handler) as mock_method:
            await user.press_button_with_text('Tilastot')
            mock_method.assert_called_once()

            # Message should now have updated information that the activity has been timed out
            self.assertIn('Toimenpide aikakatkaistu ⌛', chat.last_bot_txt())

            # There should not be any buttons anymore
            expected_buttons = []
            actual_buttons = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
            self.assertEqual(expected_buttons, actual_buttons)


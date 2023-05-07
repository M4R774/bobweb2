import os

import openai
from django.test import TestCase
from unittest import mock

from telegram import Voice

from bobweb.bob import openai_api_utils, database, command_gpt
from bobweb.bob.command_gpt import GptCommand
from bobweb.bob.command_image_generation import DalleCommand
from bobweb.bob.openai_api_utils import ResponseGenerationException, image_generation_prices
from bobweb.bob.test_audio_transcribing import openai_api_mock_response_with_transcription, create_mock_voice
from bobweb.bob.test_command_gpt import init_chat_with_bot_cc_holder_and_another_user, mock_response_from_openai
from bobweb.bob.test_command_image_generation import openai_api_mock_response_one_image
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockChat

# Single instance to serve all tests that need instance of GptCommand
gpt_command = command_gpt.instance
cc_holder_id = 1337  # Credit card holder id


@mock.patch('os.getenv', lambda *args: 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE')
@mock.patch('openai.ChatCompletion.create', mock_response_from_openai)
class OpenaiApiUtilsTest(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(OpenaiApiUtilsTest, cls).setUpClass()
        os.system('python bobweb/web/manage.py migrate')
        GptCommand.run_async = False
        telegram_user = database.get_telegram_user(cc_holder_id)
        database.set_credit_card_holder(telegram_user)

    def test_ensure_openai_api_key_set_raises_error_if_no_key(self):
        """
        Tests that right type of error is raised, it contains expected message and error is logged through the logger
        """
        with (
            mock.patch('os.getenv', lambda key: None),
            self.assertRaises(ResponseGenerationException) as context,
            self.assertLogs(level='ERROR') as log
        ):
            openai_api_utils.ensure_openai_api_key_set()

        self.assertEqual('OpenAI:n API-avain puuttuu ympäristömuuttujista', context.exception.response_text)
        self.assertIn('OPENAI_API_KEY is not set. No response was generated.', log.output[-1])

    def test_ensure_openai_api_key_set_updates_api_key_when_it_exists_in_env_vars(self):
        self.assertEqual('DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE', openai.api_key)

        with mock.patch('os.getenv', lambda key: 'NEW_VALUE'):
            # Now that there is a api key, this call should update it to the openai module
            openai_api_utils.ensure_openai_api_key_set()

        self.assertEqual('NEW_VALUE', openai.api_key)

    def test_when_no_cc_holder_is_set_no_one_has_permission_to_use_api(self):
        chat, cc_holder, _ = init_chat_with_bot_cc_holder_and_another_user()

        bob = database.get_the_bob()
        bob.gpt_credit_card_holder = None
        bob.save()

        self.assertFalse(openai_api_utils.user_has_permission_to_use_openai_api(cc_holder.id))

    def test_cc_holder_has_permission_to_use_api(self):
        chat, cc_holder, _ = init_chat_with_bot_cc_holder_and_another_user()
        self.assertEqual(cc_holder.id, database.get_credit_card_holder().id)

        cc_holder.send_message('/gpt this should return gpt-message')
        self.assertIn('The Los Angeles Dodgers won the World Series in 2020.', chat.last_bot_txt())

    def test_user_that_dos_not_share_group_with_cc_holder_has_no_permission_to_use_api(self):
        """ Just a new chat and new user. Has no common chats with current cc_holder so should not have permission
            to use gpt-command """
        chat, user = init_chat_user()
        self.assertNotEqual(user.id, cc_holder_id)
        user.send_message('/gpt this should give error')
        self.assertIn('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä', chat.last_bot_txt())

    def test_any_user_in_same_chat_as_cc_holder_has_permission_to_use_api(self):
        """ Create new chat and add cc_holder and another user to that chat. Now another user has permission
            to use gpt-command """
        chat, cc_holder, other_user = init_chat_with_bot_cc_holder_and_another_user()

        self.assertEqual(cc_holder.id, database.get_credit_card_holder().id)

        # Now as user_a and cc_holder are in the same chat, user_a has permission to use command
        other_user.send_message('/gpt this should return gpt-message')
        self.assertIn('The Los Angeles Dodgers won the World Series in 2020.', chat.last_bot_txt())

    def test_any_user_having_any_common_group_with_cc_holder_has_permission_to_use_api_in_any_group(self):
        """ Demonstrates, that if user has any common chat with credit card holder, they have permission to
            use command in any other chat (including private chats)"""
        chat, cc_holder, other_user = init_chat_with_bot_cc_holder_and_another_user()

        # Now, for other user create a new chat and send message in there
        new_chat = MockChat(type='private')
        other_user.send_message('/gpt new message to new chat', chat=new_chat)
        self.assertIn('The Los Angeles Dodgers won the World Series in 2020.', new_chat.last_bot_txt())

    @mock.patch('requests.post', openai_api_mock_response_with_transcription)
    @mock.patch('openai.Image.create', openai_api_mock_response_one_image)
    @mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
    def test_api_costs_are_accumulated_with_every_call_and_are_shared_between_api_call_types(self):
        # NOTE! As this is comparing floating point numbers, insted of assertEqual this calls assertAlmostEqual
        DalleCommand.run_async = False

        openai_api_utils.state.reset_cost_so_far()
        self.assertEqual(0, openai_api_utils.state.get_cost_so_far())

        # Now, init couple of chats with users
        chat_a, user_a = init_chat_user()
        user_a.send_message('/gpt babby\'s first prompt')
        self.assertAlmostEqual(0.001260, openai_api_utils.state.get_cost_so_far(), places=7)
        user_a.send_message('/gpt babby\'s second prompt')
        self.assertAlmostEqual(0.001260 * 2, openai_api_utils.state.get_cost_so_far(), places=7)
        user_a.send_message('/dalle babby\'s first image generation')
        self.assertAlmostEqual(0.001260 * 2 + 0.020, openai_api_utils.state.get_cost_so_far(), places=7)

        # Now another chat, user and command
        b_chat, b_user = init_chat_user()
        b_user.send_message('/dalle prompt from another chat by another user')
        self.assertAlmostEqual(0.001260 * 2 + 0.020 * 2, openai_api_utils.state.get_cost_so_far(), places=7)

        # And lastly, do voice transcriptions in a new chat
        with open('bobweb/bob/resources/test/telegram_voice_message_mock.ogg', "rb") as test_sound_file:
            chat_c, user_c = init_chat_user()
            chat_entity = database.get_chat(chat_c.id)
            chat_entity.voice_msg_to_text_enabled = True
            chat_entity.save()

            user_c.send_message('/tekstitä')
            voice: Voice = create_mock_voice(chat_c.bot, test_sound_file)
            user_c.send_voice(voice)

        self.assertAlmostEqual(0.001260 * 2 + 0.020 * 2 + (voice.duration / 60 * 0.006),
                               openai_api_utils.state.get_cost_so_far(), places=7)

    def test_openai_api_state_should_return_cost_message_when_cost_is_added(self):
        """ Confirms that when costs are added, amount of current request and accumulated cost is returned.
            When accumulated cost is added, it is updated in the next message """
        openai_api_utils.state.reset_cost_so_far()

        expected_cost_1 = 3 * image_generation_prices[512]
        expected_msg_1 = 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}'\
            .format(expected_cost_1, expected_cost_1)
        actual_msg = openai_api_utils.state.add_image_cost_get_cost_str(3, 512)
        self.assertEqual(expected_msg_1, actual_msg)

        expected_cost_2 = 1 * image_generation_prices[1024]
        expected_msg_2 = 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}'\
            .format(expected_cost_2, expected_cost_1 + expected_cost_2)
        actual_msg_2 = openai_api_utils.state.add_image_cost_get_cost_str(1, 1024)
        self.assertEqual(expected_msg_2, actual_msg_2)

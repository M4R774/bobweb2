import os
from typing import Tuple

import django
import openai
import pytest
import tiktoken
from django.test import TestCase
from unittest import mock

from telegram import Voice

import bobweb.bob.config
from bobweb.bob import openai_api_utils, database, command_gpt
from bobweb.bob.openai_api_utils import ResponseGenerationException, image_generation_prices, \
    tiktoken_default_encoding_name, token_count_from_message_list, gpt_4_128k, token_count_for_message, \
    find_default_gpt_model_by_version_number, remove_openai_related_command_text_and_extra_info, GptChatMessage, \
    msg_serializer_for_text_models, ContextRole, msg_serializer_for_vision_models, GptModel, \
    check_context_messages_return_suitable_model, gpt_3_16k, gpt_4_vision, upgrade_model_to_one_with_vision_capabilities
from bobweb.bob.test_audio_transcribing import openai_api_mock_response_with_transcription, create_mock_voice, \
    create_mock_converter
from bobweb.bob.test_command_gpt import mock_response_from_openai
from bobweb.bob.test_command_image_generation import openai_api_mock_response_one_image
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockChat, MockUser
from bobweb.web.bobapp.models import TelegramUser

# Single instance to serve all tests that need instance of GptCommand
gpt_command = command_gpt.instance
cc_holder_id = 1337  # Credit card holder id


async def init_chat_with_bot_cc_holder_and_another_user() -> Tuple[MockChat, MockUser, MockUser]:
    """
    Initiate chat and 2 users. One is cc_holder and other is not
    :return: chat: MockChat, cc_holder_user: MockUser, other_user: MockUser
    """
    chat = MockChat()
    user_a = MockUser(chat=chat)
    user_cc_holder = MockUser(chat=chat, id=cc_holder_id)

    # Send messages for both to persist chat and users to database
    await user_a.send_message('hi')
    await user_cc_holder.send_message('greetings')

    cc_holder = TelegramUser.objects.get(id=cc_holder_id)
    bob = database.get_the_bob()
    bob.gpt_credit_card_holder = cc_holder
    bob.save()

    return chat, user_cc_holder, user_a


@pytest.mark.asyncio
@mock.patch('bobweb.bob.async_http.post_expect_json', mock_response_from_openai)
class OpenaiApiUtilsTest(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(OpenaiApiUtilsTest, cls).setUpClass()
        os.system('python bobweb/web/manage.py migrate')
        telegram_user = database.get_telegram_user(cc_holder_id)
        database.set_credit_card_holder(telegram_user)
        bobweb.bob.config.openai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'

    async def test_ensure_openai_api_key_set_raises_error_if_no_key(self):
        """
        Tests that right type of error is raised, it contains expected message and error is logged through the logger
        """
        bobweb.bob.config.openai_api_key = None
        with (
            self.assertRaises(ResponseGenerationException) as context,
            self.assertLogs(level='ERROR') as log
        ):
            openai_api_utils.ensure_openai_api_key_set()

        self.assertEqual('OpenAI:n API-avain puuttuu ympäristömuuttujista', context.exception.response_text)
        self.assertIn('OPENAI_API_KEY is not set. No response was generated.', log.output[-1])

    async def test_ensure_openai_api_key_set_updates_api_key_when_it_exists_in_env_vars(self):
        bobweb.bob.config.openai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'
        openai_api_utils.ensure_openai_api_key_set()

        self.assertEqual('DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE', openai.api_key)

        bobweb.bob.config.openai_api_key = 'NEW_VALUE'
        # Now that there is a api key, this call should update it to the openai module
        openai_api_utils.ensure_openai_api_key_set()

        self.assertEqual('NEW_VALUE', openai.api_key)

    async def test_when_no_cc_holder_is_set_no_one_has_permission_to_use_api(self):
        chat, cc_holder, _ = await init_chat_with_bot_cc_holder_and_another_user()

        bob = database.get_the_bob()
        bob.gpt_credit_card_holder = None
        bob.save()

        self.assertFalse(openai_api_utils.user_has_permission_to_use_openai_api(cc_holder.id))

    async def test_cc_holder_has_permission_to_use_api(self):
        chat, cc_holder, _ = await init_chat_with_bot_cc_holder_and_another_user()
        self.assertEqual(cc_holder.id, database.get_credit_card_holder().id)

        await cc_holder.send_message('/gpt this should return gpt-message')
        self.assertIn('The Los Angeles Dodgers won the World Series in 2020.', chat.last_bot_txt())

    async def test_user_that_dos_not_share_group_with_cc_holder_has_no_permission_to_use_api(self):
        """ Just a new chat and new user. Has no common chats with current cc_holder so should not have permission
            to use gpt-command """
        chat, user = init_chat_user()
        self.assertNotEqual(user.id, cc_holder_id)
        await user.send_message('/gpt this should give error')
        self.assertIn('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä', chat.last_bot_txt())

    async def test_any_user_in_same_chat_as_cc_holder_has_permission_to_use_api(self):
        """ Create new chat and add cc_holder and another user to that chat. Now another user has permission
            to use gpt-command """
        chat, cc_holder, other_user = await init_chat_with_bot_cc_holder_and_another_user()

        self.assertEqual(cc_holder.id, database.get_credit_card_holder().id)

        # Now as user_a and cc_holder are in the same chat, user_a has permission to use command
        await other_user.send_message('/gpt this should return gpt-message')
        self.assertIn('The Los Angeles Dodgers won the World Series in 2020.', chat.last_bot_txt())

    async def test_any_user_having_any_common_group_with_cc_holder_has_permission_to_use_api_in_any_group(self):
        """ Demonstrates, that if user has any common chat with credit card holder, they have permission to
            use command in any other chat (including private chats)"""
        chat, cc_holder, other_user = await init_chat_with_bot_cc_holder_and_another_user()

        # Now, for other user create a new chat and send message in there
        new_chat = MockChat(type='private')
        await other_user.send_message('/gpt new message to new chat', chat=new_chat)
        self.assertIn('The Los Angeles Dodgers won the World Series in 2020.', new_chat.last_bot_txt())

    @mock.patch('bobweb.bob.async_http.post_expect_json', openai_api_mock_response_with_transcription)
    @mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
    async def test_api_costs_are_accumulated_with_every_call_and_are_shared_between_api_call_types(self):
        # NOTE! As this is comparing floating point numbers, instead of assertEqual this calls assertAlmostEqual

        openai_api_utils.state.reset_cost_so_far()
        self.assertEqual(0, openai_api_utils.state.get_cost_so_far())

        # Now, init couple of chats with users
        chat_a, user_a = init_chat_user()
        await user_a.send_message('/gpt babby\'s first prompt')
        self.assertAlmostEqual(0.00094, openai_api_utils.state.get_cost_so_far(), places=7)
        await user_a.send_message('/gpt babby\'s second prompt')
        self.assertAlmostEqual(0.00094 * 2, openai_api_utils.state.get_cost_so_far(), places=7)

        with mock.patch('openai.Image.acreate', openai_api_mock_response_one_image):
            await user_a.send_message('/dalle babby\'s first image generation')
            self.assertAlmostEqual(0.00094 * 2 + 0.020, openai_api_utils.state.get_cost_so_far(), places=7)

            # Now another chat, user and command
            b_chat, b_user = init_chat_user()
            await b_user.send_message('/dalle prompt from another chat by another user')

        self.assertAlmostEqual(0.00094 * 2 + 0.020 * 2, openai_api_utils.state.get_cost_so_far(), places=7)

        # And lastly, do voice transcriptions in a new chat
        chat_c, user_c = init_chat_user()
        voice: Voice = create_mock_voice()
        voice_msg = await user_c.send_voice(voice)

        with mock.patch('bobweb.bob.message_handler_voice.convert_buffer_content_to_audio', create_mock_converter(1)):
            await user_c.send_message('/tekstitä', reply_to_message=voice_msg)

        self.assertAlmostEqual(0.00094 * 2 + 0.020 * 2 + (voice.duration / 60 * 0.006),
                               openai_api_utils.state.get_cost_so_far(), places=7)

    async def test_openai_api_state_should_return_cost_message_when_cost_is_added(self):
        """ Confirms that when costs are added, amount of current request and accumulated cost is returned.
            When accumulated cost is added, it is updated in the next message """
        openai_api_utils.state.reset_cost_so_far()

        expected_cost_1 = 3 * image_generation_prices[512]
        expected_msg_1 = 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}' \
            .format(expected_cost_1, expected_cost_1)
        actual_msg = openai_api_utils.state.add_image_cost_get_cost_str(3, 512)
        self.assertEqual(expected_msg_1, actual_msg)

        expected_cost_2 = 1 * image_generation_prices[1024]
        expected_msg_2 = 'Rahaa paloi: ${:f}, rahaa palanut rebootin jälkeen: ${:f}' \
            .format(expected_cost_2, expected_cost_1 + expected_cost_2)
        actual_msg_2 = openai_api_utils.state.add_image_cost_get_cost_str(1, 1024)
        self.assertEqual(expected_msg_2, actual_msg_2)

    async def test_known_openai_api_commands_and_cost_info_is_removed_from_replied_message(self):
        # Removes OpenAi related commands, cost information and other stuff from the replied message
        expected_cases = [
            ('Abc', 'Abc\n\nKonteksti: 1 viesti. Rahaa paloi: $0.001260, rahaa palanut rebootin jälkeen: $0.001260'),
            ('Abc', 'Abc\n\nRahaa paloi: $0.001260, rahaa palanut rebootin jälkeen: $0.001260'),
            ('Abc', '/gpt /1 Abc'),
            ('Abc', '/dalle Abc'),
            ('Abc', '/dallemini Abc'),
            ('Abc', '"<i>Abc</i>"'),
        ]
        for case in expected_cases:
            self.assertEqual(case[0], remove_openai_related_command_text_and_extra_info(case[1]))


class TestGptModelSelectorsAndMessageSerializers(django.test.TransactionTestCase):
    """
    Uses unittest library, as these are static functions with no database connections or library dependencies.
    Uses actual Gpt Model definitions in the tests. Those are bound to have frequent changes over time so if
    some models are removed or added, tests might fail. In those cases either remove redundant tests of add
    removed models as mock-object models to be used only by the tests.
    """

    # Mock model for possible major version 5 text model
    gpt_5_mock_model = GptModel('gpt-5-1337-preview', 5, False, None, None, None, None)
    gpt_5_mock_model_with_vision = GptModel('gpt-5-vision-preview', 5, True, None, None, None, None)

    # Test message history lists
    messages_without_images = [GptChatMessage(ContextRole.USER, 'text', [])]
    messages_with_images = [GptChatMessage(ContextRole.USER, 'text', ['image_url'])]

    def test_upgrade_model_to_one_with_vision_capabilities(self):

        # Case 1: Given model already has vision capabilities
        result = upgrade_model_to_one_with_vision_capabilities(gpt_4_vision, [])
        self.assertEqual(result, gpt_4_vision)

        # Case 2: Same major version model with vision
        result = upgrade_model_to_one_with_vision_capabilities(gpt_4_128k, [gpt_4_128k, gpt_4_vision])
        self.assertEqual(result, gpt_4_vision)

        # Case 3: Nearest greater major version model with vision
        available_models = [gpt_4_128k, self.gpt_5_mock_model, self.gpt_5_mock_model_with_vision]
        result = upgrade_model_to_one_with_vision_capabilities(gpt_4_128k, available_models)
        self.assertEqual(result, self.gpt_5_mock_model_with_vision)

        # Case 4: Nearest lower major version model with vision
        available_models = [gpt_4_vision, self.gpt_5_mock_model]
        result = upgrade_model_to_one_with_vision_capabilities(self.gpt_5_mock_model, available_models)
        self.assertEqual(result, gpt_4_vision)

        # Case 5: No vision models, returns the given model
        result = upgrade_model_to_one_with_vision_capabilities(gpt_3_16k, [gpt_3_16k, gpt_4_128k])
        self.assertEqual(result, gpt_3_16k)

    def test_check_context_messages_return_correct_model(self):
        # Test cases for check_context_messages_return_correct_model

        # Case 1: Model with major version 3, returns always the same model
        result = check_context_messages_return_suitable_model(gpt_3_16k, [])
        self.assertEqual(result, gpt_3_16k)

        # Case 2: Model with major version other than 3, no images in messages
        result = check_context_messages_return_suitable_model(gpt_4_128k, [])
        self.assertEqual(result, gpt_4_128k)

        # Case 3: Model with major version other than 3, one message without images
        result = check_context_messages_return_suitable_model(gpt_4_128k, self.messages_without_images)
        self.assertEqual(result, gpt_4_128k)

        # Case 4: Model with major version other than 3, one message with an image
        result = check_context_messages_return_suitable_model(gpt_4_128k, self.messages_with_images)
        # Now returns model with vision capabilities
        self.assertEqual(result, gpt_4_vision)

        # Case 5: Model with higher version without vision capabilities,
        result = check_context_messages_return_suitable_model(self.gpt_5_mock_model, self.messages_without_images)
        # Now returns model with vision capabilities
        self.assertEqual(result, self.gpt_5_mock_model)

        # Case 5: Model with higher version without vision capabilities
        result = check_context_messages_return_suitable_model(self.gpt_5_mock_model, self.messages_without_images)
        # Now returns model with vision capabilities
        self.assertEqual(result, self.gpt_5_mock_model)

    def test_msg_serializer_for_text_models(self):
        """
        As this is serializer for models without any vision capabilities, the result never contains any image urls
        even though the source image might have had an image associated with it.
        """
        # Case 1: text is None, image_urls is empty
        message = GptChatMessage(role=ContextRole.USER, text=None)
        result = msg_serializer_for_text_models(message)
        self.assertEqual(result, {'role': 'user', 'content': ''})

        # Case 2: text is empty string, image_urls is empty
        message = GptChatMessage(role=ContextRole.USER, text='')
        result = msg_serializer_for_text_models(message)
        self.assertEqual(result, {'role': 'user', 'content': ''})

        # Case 3: text is empty string, image_urls has items
        message = GptChatMessage(role=ContextRole.USER, text='', base_64_images=['img1', 'img2'])
        result = msg_serializer_for_text_models(message)
        self.assertEqual(result, {'role': 'user', 'content': ''})

        # Case 4: text has content 'foo', image_urls is empty
        message = GptChatMessage(role=ContextRole.USER, text='foo')
        result = msg_serializer_for_text_models(message)
        self.assertEqual(result, {'role': 'user', 'content': 'foo'})

        # Case 5: different role
        message = GptChatMessage(role=ContextRole.ASSISTANT, text='foo')
        result = msg_serializer_for_text_models(message)
        self.assertEqual(result, {'role': 'assistant', 'content': 'foo'})

        # Case 6: text has content 'foo', image_urls has items
        message = GptChatMessage(role=ContextRole.USER, text='foo', base_64_images=['img1', 'img2'])
        result = msg_serializer_for_text_models(message)
        self.assertEqual(result, {'role': 'user', 'content': 'foo'})

    def test_msg_serializer_for_vision_models(self):
        """
        Vision models have a more complex structure to their messages.
        Note! Vision model has no problem with message that has no content (neither any text nor image urls).
        """

        # Case 1: text is None, image_urls is empty
        message = GptChatMessage(role=ContextRole.USER, text=None)
        result = msg_serializer_for_vision_models(message)
        self.assertEqual(result, {'role': 'user', 'content': []})

        # Case 2: text is empty string, image_urls is empty
        message = GptChatMessage(role=ContextRole.USER, text='')
        result = msg_serializer_for_vision_models(message)
        self.assertEqual(result, {'role': 'user', 'content': []})

        # Case 3: text is None, image_urls has items
        message = GptChatMessage(role=ContextRole.USER, text='', base_64_images=['img1', 'img2'])
        result = msg_serializer_for_vision_models(message)
        expected = {'role': 'user',
                    'content': [
                        {'type': 'image_url', 'image_url': {'url': 'img1'}},
                        {'type': 'image_url', 'image_url': {'url': 'img2'}}
                    ]}
        self.assertEqual(result, expected)

        # Case 4: text has content 'foo', image_urls is empty
        message = GptChatMessage(role=ContextRole.USER, text='foo')
        result = msg_serializer_for_vision_models(message)
        expected = {'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'foo'}
                    ]}
        self.assertEqual(result, expected)

        # Case 5: text has content 'foo', image_urls has items
        message = GptChatMessage(role=ContextRole.USER, text='foo', base_64_images=['img1', 'img2'])
        result = msg_serializer_for_vision_models(message)
        expected = {'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'foo'},
                        {'type': 'image_url', 'image_url': {'url': 'img1'}},
                        {'type': 'image_url', 'image_url': {'url': 'img2'}}
                    ]}
        self.assertEqual(result, expected)

        # Case 6: image_urls has both items with length and empty string and or None objects
        message = GptChatMessage(role=ContextRole.USER, text=None, base_64_images=['img1', '', None, 'img2'])
        result = msg_serializer_for_vision_models(message)
        # None or empty String urls are not included
        expected = {'role': 'user',
                    'content': [
                        {'type': 'image_url', 'image_url': {'url': 'img1'}},
                        {'type': 'image_url', 'image_url': {'url': 'img2'}}
                    ]}
        self.assertEqual(result, expected)


@pytest.mark.asyncio
class TikTokenTests(TestCase):
    """
    Tests for external dependency tiktoken. TikToken is used to count number of tokens in given message history.
    That information is used for determining the right model which token limit fits best.
    """

    def test_tiktoken_returns_same_token_count_as_openai_tokenizer(self):
        """
        OpenAi Tokenizer result taken from https://platform.openai.com/tokenizer. Tiktoken uses encoding model
        'cl100k_base' that is same for encoder used by Gpt models 3.5-turbo and 4.
        """
        text = ('Mary had a little lamb, Its fleece was white as snow (or black as coal). '
                'And everywhere that Mary went, The lamb was sure to go. He followed her to '
                'school one day, That was against the rule. It made the children laugh and '
                'play To see a lamb at school.')
        encoding = tiktoken.get_encoding(tiktoken_default_encoding_name)
        self.assertEqual(251, len(text))
        self.assertEqual(59, len(encoding.encode(text)))

    def test_openai_api_utils_message_list_token_counter(self):
        """
        Expected OpenAi token counts calculated using to https://platform.openai.com/tokenizer
        - 'Your name is Bob.': 17 characters, 5 tokens
        - 'Who won the world series in 2020?': is 33 characters and 10 tokens.
        - 'The Los Angeles Dodgers won the World Series in 2020.': 53 characters, 13 tokens.
        """
        message_history = [
            {'role': 'system', 'content': 'Your name is Bob.', },
            {'role': 'user', 'content': 'Who won the world series in 2020?'},
            {'role': 'assistant', 'content': 'The Los Angeles Dodgers won the World Series in 2020.'}
        ]
        encoding = tiktoken.get_encoding(tiktoken_default_encoding_name)

        # First make sure that each messages expected token count is correct
        self.assertEqual(5, len(encoding.encode(message_history[0]['content'])))
        self.assertEqual(10, len(encoding.encode(message_history[1]['content'])))
        self.assertEqual(13, len(encoding.encode(message_history[2]['content'])))

        # Now test token counts for the whole message item.
        # As the message object contains the role, it adds one token to the count.
        self.assertEqual(6, token_count_for_message(message_history[0], encoding))
        self.assertEqual(11, token_count_for_message(message_history[1], encoding))
        self.assertEqual(14, token_count_for_message(message_history[2], encoding))

        # this has been confirmed with real api using model 'gpt-4-0613': prompt_token count for request
        # with only first 2 messages is 26 in total.
        # Now when counting token count for messages list, constant start value is 3.
        # Then each messages token count is 3 + its message object token count (content + role).
        # So in this case, it's 3 + 2*3 + 6 + 11 = 26
        self.assertEqual(26, token_count_from_message_list(message_history[:2], gpt_4_128k))

        # For the whole list, same calculation is applied:
        # 3 + 3*3 + 6 + 11 + 14 = 43
        self.assertEqual(43, token_count_from_message_list(message_history, gpt_4_128k))

    def test_find_gpt_model_name_by_version_number(self):
        """
        Tests that find_gpt_model_name_by_version_number returns correct version of model
        that can fit whole conversation context if possible.
        """
        messages = [
            {'role': 'user', 'content': 'Who won the world series in 2020?'},
            {'role': 'assistant', 'content': 'The Los Angeles Dodgers won the World Series in 2020.'}
        ]
        # As these two messages are total of 34 tokens, for major model version 3.5 should
        # return 4k context minor version and for major version 4 should return 128k context
        # limit version.
        self.assertEqual('gpt-3.5-turbo-1106', find_default_gpt_model_by_version_number('3.5').name)
        self.assertEqual('gpt-4-1106-preview', find_default_gpt_model_by_version_number('4').name)

        # With context over 4k, should user 16k model for gpt 3.5
        messages_5k = messages * 150  # 34 * 150 = 5100 tokens
        self.assertEqual('gpt-3.5-turbo-1106', find_default_gpt_model_by_version_number('3.5').name)
        self.assertEqual('gpt-4-1106-preview', find_default_gpt_model_by_version_number('4').name)

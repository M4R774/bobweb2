import os
from typing import Tuple

import django
import pytest
from django.test import TestCase
from unittest import mock

import bobweb.bob.config
from bobweb.bob import main, openai_api_utils, database, command_gpt, config
from bobweb.bob.openai_api_utils import ResponseGenerationException, \
    remove_openai_related_command_text_and_extra_info, GptChatMessage, \
    msg_serializer_for_text_models, ContextRole, msg_serializer_for_vision_models, GptModel, \
    determine_suitable_model_for_version_based_on_message_history, gpt_4o, upgrade_model_to_one_with_vision_capabilities
from bobweb.bob.test_command_gpt import mock_response_from_openai
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
@mock.patch('bobweb.bob.async_http.post', mock_response_from_openai)
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

        self.assertEqual('OpenAI API key is missing from environment variables', context.exception.response_text)
        self.assertIn('OPENAI_API_KEY is not set. No response was generated.', log.output[-1])

    async def test_ensure_openai_api_key_set_updates_api_key_when_it_exists_in_env_vars(self):
        bobweb.bob.config.openai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'
        openai_api_utils.ensure_openai_api_key_set()

        self.assertEqual('DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE', config.openai_api_key)

        bobweb.bob.config.openai_api_key = 'NEW_VALUE'
        # Now that there is a api key, this call should update it to the openai module
        openai_api_utils.ensure_openai_api_key_set()

        self.assertEqual('NEW_VALUE', config.openai_api_key)

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
        self.assertIn('gpt answer', chat.last_bot_txt())

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
        self.assertIn('gpt answer', chat.last_bot_txt())

    async def test_any_user_having_any_common_group_with_cc_holder_has_permission_to_use_api_in_any_group(self):
        """ Demonstrates, that if user has any common chat with credit card holder, they have permission to
            use command in any other chat (including private chats)"""
        chat, cc_holder, other_user = await init_chat_with_bot_cc_holder_and_another_user()

        # Now, for other user create a new chat and send message in there
        new_chat = MockChat(type='private')
        await other_user.send_message('/gpt new message to new chat', chat=new_chat)
        self.assertIn('gpt answer', new_chat.last_bot_txt())

    async def test_known_openai_api_commands_and_cost_info_is_removed_from_replied_message(self):
        # Removes OpenAi related commands, cost information and other stuff from the replied message
        # Update 12/2024: Now bot no longer adds cost information to the replied message. However, as there are old
        # messages with cost information that the user might reply, this test is kept as it assures that the cost
        # information part is still removed as expected.
        expected_cases = [
            ('Abc', 'Abc\n\nKonteksti: 1 viesti. Rahaa paloi: $0.001260, rahaa palanut rebootin jälkeen: $0.001260'),
            ('Abc', 'Abc\n\nRahaa paloi: $0.001260, rahaa palanut rebootin jälkeen: $0.001260'),
            ('Abc', '/gpt /1 Abc'),
            ('Abc', '/dalle Abc'),
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
    gpt_5_mock_model_no_vision = GptModel('gpt-5-1337-preview', 5, False, None, None)
    gpt_5_mock_model_with_vision = GptModel('gpt-5-vision-preview', 5, True, None, None)

    # Test message history lists
    messages_without_images = [GptChatMessage(ContextRole.USER, 'text', [])]
    messages_with_images = [GptChatMessage(ContextRole.USER, 'text', ['image_url'])]

    def test_check_context_messages_return_correct_model(self):
        # Test cases for check_context_messages_return_correct_model
        # Case 2: Model with major version other than 3, no images in messages
        result = determine_suitable_model_for_version_based_on_message_history('4', [])
        self.assertEqual(result, gpt_4o)

        # Case 3: Model with major version other than 3, one message without images
        result = determine_suitable_model_for_version_based_on_message_history('4', self.messages_without_images)
        self.assertEqual(result, gpt_4o)

        # Case 4: Model with major version other than 3, one message with an image
        result = determine_suitable_model_for_version_based_on_message_history('4', self.messages_with_images)
        # Now returns model with vision capabilities
        self.assertEqual(result, gpt_4o)

        # Case 5: Model that is not supported
        result = determine_suitable_model_for_version_based_on_message_history('5', self.messages_without_images)
        # Now returns gpt 4 model
        self.assertEqual(result, gpt_4o)

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

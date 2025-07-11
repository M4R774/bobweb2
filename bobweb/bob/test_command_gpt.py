import base64
import os
from unittest.mock import AsyncMock

import pytest
from django.core import management
from django.test import TestCase
from unittest import mock

from telegram import PhotoSize
from telegram.constants import ParseMode

import bobweb
from bobweb.bob import main, database, command_gpt, openai_api_utils, tests_utils
from bobweb.bob.openai_api_utils import ResponseGenerationException
from bobweb.bob.test_command_speech import openai_service_unavailable_error, \
    openai_api_rate_limit_error
from bobweb.bob.tests_mocks_v2 import MockTelethonClientWrapper, init_chat_user, MockMessage

from bobweb.bob.command_gpt import GptCommand, generate_help_message, \
    remove_gpt_command_related_text, determine_used_model

import django

from bobweb.bob.tests_utils import assert_command_triggers, assert_get_parameters_returns_expected_value, \
    get_json, mock_openai_http_response, mock_google_genai_http_response
from bobweb.web.bobapp.models import Chat

GOOGLE_API_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'bobweb.web.web.settings'
)

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
django.setup()


class MockOpenAIObject:
    def __init__(self):
        self.choices = [Choice()]
        self.usage = Usage()


class Choice:
    def __init__(self):
        self.message = Message()


class Message:
    def __init__(self):
        self.content = 'gpt answer'
        self.role = 'assistant'


class Usage:
    def __init__(self):
        self.prompt_tokens = 16
        self.completion_tokens = 26
        self.total_tokens = 42


def assert_gpt_api_called_with(mock_method: AsyncMock, model: str, messages: list[dict[str, str]],
                               url: str = 'https://api.openai.com/v1/chat/completions'):
    """
    Helper method for determining on how OpenAi http API endpoint was called. Added when Gpt was switched
    from openai python library to direct http requests.
    """
    mock_method.assert_called_with(
        url=url,
        headers={'Authorization': 'Bearer DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'},
        json={'model': model, 'messages': messages}
    )


def single_user_message_context(message: str) -> list[dict[str, str]]:
    return [{'role': 'user', 'content': [{'type': 'text', 'text': message}]}]


mock_response_from_openai = mock_openai_http_response(status=200, response_json_body=get_json(MockOpenAIObject()))

google_genai_missing_content = mock_google_genai_http_response(
    status=200, response_json_body=[{'choices': [{'message': {}}]}])

google_genai_invalid_argument = mock_google_genai_http_response(
    status=400, response_json_body=[{'error': {'code': '', 'status': 'INVALID_ARGUMENT', 'message': ''}}])

google_genai_failed_precondition = mock_google_genai_http_response(
    status=400, response_json_body=[{'error': {'code': '', 'status': 'FAILED_PRECONDITION', 'message': ''}}])

google_genai_permission_denied = mock_google_genai_http_response(
    status=403, response_json_body=[{'error': {'code': '', 'status': 'PERMISSION_DENIED', 'message': ''}}])

google_genai_not_found = mock_google_genai_http_response(
    status=404, response_json_body=[{'error': {'code': '', 'status': 'NOT_FOUND', 'message': ''}}])

google_genai_resource_exhausted = mock_google_genai_http_response(
    status=429, response_json_body=[{'error': {'code': '', 'status': 'RESOURCE_EXHAUSTED', 'message': ''}}])

google_genai_internal = mock_google_genai_http_response(
    status=500, response_json_body=[{'error': {'code': '', 'status': 'INTERNAL', 'message': ''}}])

google_genai_unavailable = mock_google_genai_http_response(
    status=503, response_json_body=[{'error': {'code': '', 'status': 'UNAVAILABLE', 'message': ''}}])

google_genai_deadline_exceed = mock_google_genai_http_response(
    status=504, response_json_body=[{'error': {'code': '', 'status': 'DEADLINE_EXCEEDED', 'message': ''}}])


async def raises_response_generation_exception(*args, **kwargs):
    raise ResponseGenerationException('response generation raised an exception')


@mock.patch('bobweb.bob.async_http.post', mock_response_from_openai)
@mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
@pytest.mark.asyncio
class ChatGptCommandTests(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(ChatGptCommandTests, cls).setUpClass()
        django.setup()
        management.call_command('migrate')
        bobweb.bob.config.openai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'
        bobweb.bob.config.google_genai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'

    async def test_command_triggers(self):
        should_trigger = ['/gpt', '!gpt', '.gpt', '/GPT', '/gpt test',
                          '/gpt4', '/gpt 4', '/gpt /4',
                          '/gpt4o', '/gpt 4o', '/gpt /4o',
                          '/gpto1', '/gpt o1', '/gpt /o1',
                          '/gpto1-mini', '/gpt o1-mini', '/gpt /o1-mini',
                          '/gptmini', '/gpt mini', '/gpt /mini']
        should_not_trigger = ['gpt', 'test /gpt', '/gpt2', '/gpt3.0', '/gpt3', '/gpt3.5', '/gpt4.0', '/gpt5']
        await assert_command_triggers(self, GptCommand, should_trigger, should_not_trigger)

    async def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!gpt', command_gpt.instance)

    async def test_help_prompt_gives_help_reply(self):
        chat, user = init_chat_user()
        await user.send_message('first message')
        expected_reply = generate_help_message(chat.id)

        # Nothing but the command (not reply to any message not or contains an image)
        actual_message: MockMessage = await tests_utils.assert_reply_equal(self, '/gpt', expected_reply)
        self.assertEqual(ParseMode.HTML, actual_message.parse_mode)

        # Contains help
        await tests_utils.assert_reply_equal(self, '/gpt help', expected_reply)
        await tests_utils.assert_reply_equal(self, '/gpt /help', expected_reply)

        # Contains quick system usage sub command but no prompt
        await tests_utils.assert_reply_equal(self, '/gpt /1', expected_reply)
        await tests_utils.assert_reply_equal(self, '/gpt 1', expected_reply)

    async def test_help_message_no_system_or_quic_system_messages(self):
        chat, user = init_chat_user()
        await user.send_message('.gpt help')
        self.assertIn(command_gpt.no_system_prompt_paragraph, generate_help_message(chat.id))
        self.assertIn(command_gpt.no_quick_system_prompts_paragraph, generate_help_message(chat.id))

    async def test_help_message_user_given_content_is_html_escaped(self):
        chat, user = init_chat_user()
        await user.send_message('.gpt .system `<script>` && `<code>`')
        expected_current_system_message_part = \
            ('<b>Tämän chatin järjestelmäviesti on:</b>\n'
             '"""\n'
             '<i>`&lt;script&gt;` &amp;&amp; `&lt;code&gt;`</i>\n'
             '"""')
        self.assertIn(expected_current_system_message_part, generate_help_message(chat.id))

    async def test_quick_system_messages_are_html_escaped_as_well(self):
        chat, user = init_chat_user()
        await user.send_message('/gpt /1 = Normal system message to show format')
        await user.send_message('.gpt .2 = `<script>` && `<code>`')
        expected_current_system_message_part = \
            ('<b>Tämän chatin pikajärjestelmäviestit ovat:</b>\n'
             '"""\n'
             '- 1: "<i>Normal system message to show format</i>"\n'
             '- 2: "<i>`&lt;script&gt;` &amp;&amp; `&lt;code&gt;`</i>"\n'
             '"""')
        self.assertIn(expected_current_system_message_part, generate_help_message(chat.id))

    async def test_should_contain_correct_response(self):
        chat, user = init_chat_user()
        await user.send_message('/gpt gpt prompt')
        expected_reply = 'gpt answer'
        self.assertEqual(expected_reply, chat.last_bot_txt())

    async def test_set_new_system_prompt(self):
        chat, user = init_chat_user()
        # Can be set with either command prefix or without
        await user.send_message('!gpt !system system message 1')
        self.assertEqual('System-viesti asetettu annetuksi.', chat.last_bot_txt())

        await user.send_message('!gpt system system message 2')
        self.assertEqual('System-viesti asetettu annetuksi.', chat.last_bot_txt())

        actual_system_prompt = Chat.objects.get(id=chat.id).gpt_system_prompt
        self.assertEqual('system message 2', actual_system_prompt)

    async def test_each_command_without_replied_messages_is_in_its_own_context(self):
        chat, user = init_chat_user()
        # 3 commands are sent. Each has context of 1 message
        for i in range(1, 4):
            mock_method = AsyncMock()
            with (
                mock.patch('bobweb.bob.async_http.post', mock_method),
                mock.patch('random.random', return_value=0.51)
            ):
                prompt = f'Prompt no. {i}'
                await user.send_message(f'.gpt {prompt}')
                assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=single_user_message_context(prompt))

    async def test_context_content(self):
        """ A little bit more complicated test. Tests that messages in reply threads are included
            in the next replies message context as expected. Here we create first a chain of
            three gpt-command that each are replies to previous commands answer from bot. Each
            bots answer is reply to the command that triggered it. So there is a continuous
            reply-chain from the first gpt-command to the last reply from bot"""
        chat, user = init_chat_user()
        await user.send_message('.gpt .system system message')
        self.assertEqual('System-viesti asetettu annetuksi.', chat.last_bot_txt())
        prev_msg_reply = None

        # Use mock telethon client wrapper that does not try to use real library but instead a mock
        # that searches mock-objects from initiated chats bot-objects collections
        with (
            mock.patch('bobweb.bob.telethon_service.client', MockTelethonClientWrapper(chat.bot)),
            mock.patch('random.random', return_value=0.51)
        ):
            for i in range(1, 4):
                # Send 3 messages where each message is reply to the previous one
                await user.send_message(f'.gpt message {i}', reply_to_message=prev_msg_reply)
                prev_msg_reply = chat.last_bot_msg()

            # Now that we have create a chain of 6 messages (3 commands, and 3 answers), add
            # one more reply to the chain and check, that the MockApi is called with all previous
            # messages in the context (in addition to the system message)
            mock_method = AsyncMock()
            with mock.patch('bobweb.bob.async_http.post', mock_method):
                await user.send_message('/gpt gpt prompt', reply_to_message=prev_msg_reply)

            expected_call_args_messages = [
                {'role': 'system', 'content': [{'type': 'text', 'text': 'system message'}]},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'message 1'}]},
                {'role': 'assistant', 'content': [{'type': 'text', 'text': 'gpt answer'}]},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'message 2'}]},
                {'role': 'assistant', 'content': [{'type': 'text', 'text': 'gpt answer'}]},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'message 3'}]},
                {'role': 'assistant', 'content': [{'type': 'text', 'text': 'gpt answer'}]},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'gpt prompt'}]}
            ]
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_call_args_messages)

    async def test_no_system_message(self):
        chat, user = init_chat_user()
        mock_method = mock_openai_http_response(status=200, response_json_body=get_json(MockOpenAIObject()))
        with (
            mock.patch('bobweb.bob.telethon_service.client', MockTelethonClientWrapper(chat.bot)),
            mock.patch('bobweb.bob.async_http.post', mock_method),
            mock.patch('random.random', return_value=0.51)
        ):
            await user.send_message('.gpt test')
            expected_call_args_messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'test'}]}]
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_call_args_messages)

            # Now, if system message is added, it is included in call after that
            await user.send_message('.gpt .system system message')
            await user.send_message('.gpt test2')
            expected_call_args_messages = [
                {'role': 'system', 'content': [{'type': 'text', 'text': 'system message'}]},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'test2'}]}
            ]
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_call_args_messages)

    async def test_gpt_command_without_any_message_as_reply_to_another_message(self):
        """
        Tests that if user replies to another message with just '/gpt' command, then that
        other message (and any messages in the reply chain) are included in the api calls
        context message history. The '/gpt' command message itself is not included, as it
        contains nothing else than the command itself.
        """
        chat, user = init_chat_user()
        mock_method = mock_openai_http_response(status=200, response_json_body=get_json(MockOpenAIObject()))
        with (
            mock.patch('bobweb.bob.telethon_service.client', MockTelethonClientWrapper(chat.bot)),
            mock.patch('bobweb.bob.async_http.post', mock_method),
            mock.patch('random.random', return_value=0.51)
        ):
            original_message = await user.send_message('some message')
            gpt_command_message = await user.send_message('.gpt', reply_to_message=original_message)
            expected_call_args_messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'some message'}]}]
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_call_args_messages)

            # Now, if there is just a gpt-command in the reply chain, that message is excluded from
            # the context message history for later calls
            await user.send_message('/gpt something else', reply_to_message=gpt_command_message)
            expected_call_args_messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'some message'}]},
                                           {'role': 'user', 'content': [{'type': 'text', 'text': 'something else'}]}]
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_call_args_messages)

    async def test_prints_system_prompt_if_sub_command_given_without_parameters(self):
        # Create a new chat. Expect bot to tell, that system msg is empty
        chat, user = init_chat_user()
        await user.send_message('/gpt /system')
        self.assertIn('Nykyinen system-viesti on nyt tyhjä', chat.last_bot_txt())

        # Now set system message for chat and check that it is contained in the response
        chat_entity = Chat.objects.get(id=chat.id)
        chat_entity.gpt_system_prompt = '_system_prompt_'
        chat_entity.save()

        await user.send_message('/gpt /system')
        self.assertIn('Nykyinen system-viesti on nyt:\n\n_system_prompt_', chat.last_bot_txt())

    async def test_system_prompt_can_be_updated_with_sub_command(self):
        # Create a new chat. Expect bot to tell, that system msg is empty
        chat, user = init_chat_user()
        await user.send_message('/gpt /system')
        self.assertIn('Nykyinen system-viesti on nyt tyhjä', chat.last_bot_txt())

        # Give command to update system message, check from database that it has been updated
        await user.send_message('/gpt /system _new_system_prompt_')

        chat_entity = Chat.objects.get(id=chat.id)
        self.assertEqual('_new_system_prompt_', chat_entity.gpt_system_prompt)

    async def test_system_prompt_is_chat_specific(self):
        # Initiate 2 different chats that have cc-holder as member
        # cc-holder user is ignored as it's not needed in this test case
        chat_a, user_a = init_chat_user()
        b_chat, b_user = init_chat_user()

        # Both users send message with gpt command to their corresponding chats
        await user_a.send_message('/gpt /system')
        await b_user.send_message('/gpt /system')

        self.assertIn('Nykyinen system-viesti on nyt tyhjä', chat_a.last_bot_txt())
        self.assertIn('Nykyinen system-viesti on nyt tyhjä', b_chat.last_bot_txt())

        # Update chat a system message and check that it has changed in the database, but chat b has not
        await user_a.send_message('/gpt /system AAA')
        self.assertEqual('AAA', Chat.objects.get(id=chat_a.id).gpt_system_prompt)
        self.assertIsNone(Chat.objects.get(id=b_chat.id).gpt_system_prompt)

        # Update chat b system message and check that it has changed in the database
        await b_user.send_message('/gpt /system B')
        self.assertEqual('AAA', Chat.objects.get(id=chat_a.id).gpt_system_prompt)
        self.assertEqual('B', Chat.objects.get(id=b_chat.id).gpt_system_prompt)

    async def test_quick_system_prompt(self):
        mock_method = mock_openai_http_response(status=200, response_json_body=get_json(MockOpenAIObject()))
        with (
            mock.patch('bobweb.bob.async_http.post', mock_method),
            mock.patch('random.random', return_value=0.51)
        ):
            chat, user = init_chat_user()
            await user.send_message('hi')  # Saves user and chat to the database
            chat_entity = Chat.objects.get(id=chat.id)
            chat_entity.quick_system_prompts = {'1': 'quick system message'}
            chat_entity.save()
            await user.send_message('/gpt /1 gpt prompt')

            expected_call_args = [{'role': 'system', 'content': [{'type': 'text', 'text': 'quick system message'}]},
                                  {'role': 'user', 'content': [{'type': 'text', 'text': 'gpt prompt'}]}]
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_call_args)

    async def test_another_quick_system_prompt(self):
        mock_method = mock_openai_http_response(status=200, response_json_body=get_json(MockOpenAIObject()))
        with (
            mock.patch('bobweb.bob.async_http.post', mock_method),
            mock.patch('random.random', return_value=0.51)
        ):
            chat, user = init_chat_user()
            await user.send_message('hi')  # Saves user and chat to the database
            chat_entity = Chat.objects.get(id=chat.id)
            chat_entity.quick_system_prompts = {'2': 'quick system message'}
            chat_entity.save()
            await user.send_message('/gpt /2 gpt prompt')

            expected_system_message = {'role': 'system',
                                       'content': [{'type': 'text', 'text': 'quick system message'}]}
            expected_user_message = {'role': 'user',
                                     'content': [{'type': 'text', 'text': 'gpt prompt'}]}
            expected_messages = [expected_system_message, expected_user_message]
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_messages)

    async def test_empty_prompt_after_quick_system_prompt(self):
        chat, user = init_chat_user()
        await user.send_message('/gpt /1')
        expected_reply = generate_help_message(chat.id)
        self.assertEqual(expected_reply, chat.last_bot_txt())

    async def test_set_new_quick_system_prompt(self):
        chat, user = init_chat_user()
        await user.send_message('/gpt /1 = new prompt')
        self.assertEqual('Uusi pikaohjausviesti 1 asetettu.', chat.last_bot_txt())
        expected_quick_system_prompts = {'1': 'new prompt'}
        quick_system_prompts = database.get_quick_system_prompts(chat.id)
        self.assertEqual(expected_quick_system_prompts, quick_system_prompts)

    async def test_set_new_quick_system_prompt_can_have_any_amount_of_whitespace_around_equal_sign(self):
        chat, user = init_chat_user()
        await user.send_message('/gpt /1= new prompt two')
        self.assertEqual('Uusi pikaohjausviesti 1 asetettu.', chat.last_bot_txt())
        await user.send_message('/gpt /1 =new prompt two')
        self.assertEqual('Uusi pikaohjausviesti 1 asetettu.', chat.last_bot_txt())
        await user.send_message('/gpt /1=new prompt two')
        self.assertEqual('Uusi pikaohjausviesti 1 asetettu.', chat.last_bot_txt())
        await user.send_message('/gpt /1 = new prompt two')
        self.assertEqual('Uusi pikaohjausviesti 1 asetettu.', chat.last_bot_txt())

    async def test_empty_set_quick_system_message_should_trigger_help_message_if_no_quick_system_message(self):
        chat, user = init_chat_user()
        await user.send_message('/gpt /1 =')
        expected_reply = 'Nykyinen pikaohjausviesti 1 on nyt tyhjä. ' \
                         'Voit asettaa pikaohjausviestin sisällön komennolla \'/gpt 1 = (uusi viesti)\'.'
        self.assertEqual(expected_reply, chat.last_bot_txt())

    async def test_empty_set_quick_system_message_should_show_existing_quick_system_message(self):
        chat, user = init_chat_user()
        await user.send_message('/gpt /1 = already saved prompt')
        await user.send_message('/gpt /1 =')
        expected_reply = 'Nykyinen pikaohjausviesti 1 on nyt:' \
                         '\n\nalready saved prompt'
        self.assertEqual(expected_reply, chat.last_bot_txt())

    def test_determine_used_model_based_on_command_and_context(self):
        self.assertEqual('gpt-4o', determine_used_model('/gpt test').name)
        self.assertEqual('gpt-4o', determine_used_model('/gpt4 test').name)
        self.assertEqual('gpt-4o', determine_used_model('/gpt 4 test').name)
        self.assertEqual('gpt-4o', determine_used_model('/gpt /4 test').name)

        self.assertEqual('o1-preview', determine_used_model('/gpto1 test').name)
        self.assertEqual('o1-preview', determine_used_model('/gpt o1 test').name)
        self.assertEqual('o1-preview', determine_used_model('/gpt /o1 test').name)

        self.assertEqual('o1-mini', determine_used_model('/gpto1mini test').name)
        self.assertEqual('o1-mini', determine_used_model('/gpto1-mini test').name)
        self.assertEqual('o1-mini', determine_used_model('/gptmini test').name)
        self.assertEqual('o1-mini', determine_used_model('/gpt o1mini test').name)
        self.assertEqual('o1-mini', determine_used_model('/gpt o1-mini test').name)
        self.assertEqual('o1-mini', determine_used_model('/gpt mini test').name)
        self.assertEqual('o1-mini', determine_used_model('/gpt /o1mini test').name)
        self.assertEqual('o1-mini', determine_used_model('/gpt /o1-mini test').name)
        self.assertEqual('o1-mini', determine_used_model('/gpt /mini test').name)

    def test_remove_gpt_command_related_text(self):
        """ Tests, that users gpt-command and possible system message parameter is removed """
        # Different possible model selections
        self.assertEqual('test', remove_gpt_command_related_text('/gpt test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt4 test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt 4 test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt /4 test'))

        self.assertEqual('test', remove_gpt_command_related_text('/gpto1 test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt o1 test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt /o1 test'))

        self.assertEqual('test', remove_gpt_command_related_text('/gpto1mini test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpto1-mini test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gptmini test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt o1mini test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt o1-mini test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt mini test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt /o1mini test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt /o1-mini test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt /mini test'))

        # Different quick system message selections
        self.assertEqual('test', remove_gpt_command_related_text('/gpt /1 test'))
        self.assertEqual('test', remove_gpt_command_related_text('/gpt 1 test'))

    async def test_given_model_version_is_in_openai_api_call_and_excluded_from_prompt(self):
        chat, user = init_chat_user()

        mock_method = mock_openai_http_response(status=200, response_json_body=get_json(MockOpenAIObject()))
        with (
            mock.patch('bobweb.bob.async_http.post', mock_method),
            mock.patch('random.random', return_value=0.51)
        ):
            expected_message_with_vision = [{'role': 'user', 'content': [{'type': 'text', 'text': 'test'}]}]

            await user.send_message('/gpt test')
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_message_with_vision)
            await user.send_message('/gpto1 test')
            assert_gpt_api_called_with(mock_method, model='o1-preview', messages=expected_message_with_vision)

    async def test_message_with_image(self):
        """
        Case where user sends a gpt command message with an image and then replies to it with another message.
        Bot should contain same base64 string for the image in both of the requests
        """
        chat, user = init_chat_user()

        mock_method = mock_openai_http_response(status=200, response_json_body=get_json(MockOpenAIObject()))
        mock_image_bytes = b'\0'
        mock_telethon_client = MockTelethonClientWrapper(chat.bot)
        mock_telethon_client.image_bytes_to_return = [mock_image_bytes]
        with (
            mock.patch('bobweb.bob.async_http.post', mock_method),
            mock.patch('bobweb.bob.telethon_service.client', mock_telethon_client),
            mock.patch('random.random', return_value=0.51)
        ):
            photo = (PhotoSize('1', '1', 1, 1, 1),)  # Tuple of PhotoSize objects
            initial_message = await user.send_message('/gpt foo', photo=photo)

            # Now message history list should have the image url in it
            base64_encoded_bytes = base64.b64encode(b'\0').decode('utf-8')
            expected_initial_message = {'role': 'user',
                                        'content': [
                                            {'type': 'text', 'text': 'foo'},
                                            {'type': 'image_url',
                                             'image_url': {'url': 'data:image/jpeg;base64,' + base64_encoded_bytes}}
                                        ]}
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=[expected_initial_message])

            # Bots response is now ignored and the user replies to their previous message.
            # Should have same content as previously with the image in the message.
            # Users new message has been added to the history

            await user.send_message('/gpt bar', reply_to_message=initial_message)
            expected_messages = [
                expected_initial_message,  # Same message as previously
                {'role': 'user',
                 'content': [
                     {'type': 'text', 'text': 'bar'}]}
            ]
            assert_gpt_api_called_with(mock_method, model='gpt-4o', messages=expected_messages)

    async def test_request_for_model_without_vision_capabilities_and_context_containing_images(self):
        chat, user = init_chat_user()

        mock_method = mock_openai_http_response(status=200, response_json_body=get_json(MockOpenAIObject()))
        mock_image_bytes = b'\0'
        mock_telethon_client = MockTelethonClientWrapper(chat.bot)
        mock_telethon_client.image_bytes_to_return = [mock_image_bytes]

        with (mock.patch('bobweb.bob.async_http.post', mock_method),
              mock.patch('bobweb.bob.telethon_service.client', mock_telethon_client)):
            photo = (PhotoSize('1', '1', 1, 1, 1),)  # Tuple of PhotoSize objects
            initial_message = await user.send_message('/gpt foo', photo=photo)

            await user.send_message('/gpto1 bar', reply_to_message=initial_message)
            self.assertIn(openai_api_utils.no_vision_capabilities, chat.last_bot_txt())

    async def test_client_response_generation_error(self):
        chat, user = init_chat_user()
        with mock.patch('bobweb.bob.command_gpt.generate_and_format_result_text', raises_response_generation_exception):
            await user.send_message('/gpt test')

        self.assertIn('response generation raised an exception', chat.last_bot_txt())

    async def test_service_unavailable_error(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', openai_service_unavailable_error),
            mock.patch('random.random', return_value=0.51)
        ):
            await user.send_message('/gpt test')

        self.assertIn('OpenAi:n palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut.',
                      chat.last_bot_txt())

    async def test_rate_limit_error(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', openai_api_rate_limit_error),
            mock.patch('random.random', return_value=0.51)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Käytettävissä oleva kiintiö on käytetty.',
                      chat.last_bot_txt())

    async def test_service_google_response_ok_but_missing_content(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_missing_content),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Googlen palvelu ei toimittanut.',
                      chat.last_bot_txt())

    async def test_service_google_invalid_argument(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_invalid_argument),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Virhe keskustelun syöttämisessä Googlelle.',
                      chat.last_bot_txt())

    async def test_service_google_failed_precondition(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_failed_precondition),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Virhe maksutiedoissa.',
                      chat.last_bot_txt())

    async def test_service_google_permission_denied(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_permission_denied),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Virhe autentikoitumisessa Googlen järjestelmään.',
                      chat.last_bot_txt())

    async def test_service_google_not_found(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_not_found),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Kysymyksistä tippui media matkalla.',
                      chat.last_bot_txt())

    async def test_service_google_resource_exhausted(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_resource_exhausted),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Käytettävissä oleva kiintiö on käytetty.',
                      chat.last_bot_txt())

    async def test_service_google_internal(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_internal),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Googlen palvelussa tapahtui sisäinen virhe.',
                      chat.last_bot_txt())

    async def test_service_google_unavailable(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_unavailable),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Googlen palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut. '
                      'Ole hyvä ja yritä hetken päästä uudelleen.',
                      chat.last_bot_txt())

    async def test_service_google_deadline_exceed(self):
        chat, user = init_chat_user()
        with (
            mock.patch('bobweb.bob.async_http.post', google_genai_deadline_exceed),
            mock.patch('random.random', return_value=0.49)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Googlen mielestä miettiminen kesti liikaa. Kokeile lyhyempää kysymystä.',
                      chat.last_bot_txt())


def get_cost_str(prompt_count: int) -> str:
    return format_money(prompt_count * 0.000470)


def format_money(money: float) -> str:
    return '{:f}'.format(money)

import base64
from unittest.mock import AsyncMock

import pytest
import django.test
from unittest import mock

from telegram import PhotoSize
from telegram.constants import ParseMode

import bot
from bot import main, database, openai_api_utils, tests_utils
from bot.commands import gpt
from bot.litellm_utils import ResponseGenerationException
from bot.tests_mocks_v2 import MockTelethonClientWrapper, init_chat_user, MockMessage

from bot.commands.gpt import GptCommand, generate_help_message, \
    remove_gpt_command_related_text, SYSTEM_MESSAGE_SET

import django

from bot.tests_utils import assert_command_triggers, assert_get_parameters_returns_expected_value
from web.bobapp.models import Chat

from litellm import ServiceUnavailableError

TELETHON_SERVICE_CLIENT = 'bot.telethon_service.client'

LITELLM_ACOMPLETION = 'bot.litellm_utils.litellm.acompletion'

test_model_name = 'gemini/gemini-3-pro-preview'


class MockLiteLLMResponseObject:
    def __init__(self):
        self.choices = [Choices()]
        self.usage = Usage()


class Choices:
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


def single_user_message_context(message: str) -> list[dict[str, str]]:
    return [{'role': 'user', 'content': [{'type': 'text', 'text': message}]}]


async def raises_response_generation_exception(*args, **kwargs):
    raise ResponseGenerationException('response generation raised an exception')


# NOSONAR (S1192)
@mock.patch(LITELLM_ACOMPLETION, AsyncMock(return_value=MockLiteLLMResponseObject()))
@mock.patch('bot.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
@pytest.mark.asyncio
class ChatGptCommandTests(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(ChatGptCommandTests, cls).setUpClass()
        bot.config.openai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'
        bot.config.gemini_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'

    async def test_command_triggers(self):
        should_trigger = ['/gpt', '!gpt', '.gpt', '/GPT', '/gpt test',
                          '/gpt5', '/gpt 5', '/gpt /5',
                          '/gpt4', '/gpt 4', '/gpt /4',
                          '/gpt4o', '/gpt 4o', '/gpt /4o',
                          '/gpto1', '/gpt o1', '/gpt /o1',
                          '/gpto1-mini', '/gpt o1-mini', '/gpt /o1-mini',
                          '/gptmini', '/gpt mini', '/gpt /mini']
        should_not_trigger = ['gpt', 'test /gpt', '/gpt2', '/gpt3.0', '/gpt3', '/gpt3.5', '/gpt4.0', '/gpt6']
        await assert_command_triggers(self, GptCommand, should_trigger, should_not_trigger)

    async def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!gpt', gpt.instance)

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
        self.assertIn(gpt.no_system_prompt_paragraph, generate_help_message(chat.id))
        self.assertIn(gpt.no_quick_system_prompts_paragraph, generate_help_message(chat.id))

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

    async def test_should_use_default_model_when_assigned_so(self):
        _, user = init_chat_user()
        mock_method = AsyncMock(return_value=MockLiteLLMResponseObject())
        with (
            mock.patch(LITELLM_ACOMPLETION, mock_method)
        ):
            await user.send_message('/gpt foo')
            mock_method.assert_called_with(
                model=test_model_name,
                messages=single_user_message_context('foo')
            )

    async def test_set_new_system_prompt(self):
        chat, user = init_chat_user()
        # Can be set with either command prefix or without
        await user.send_message('!gpt !system system message 1')
        self.assertEqual(SYSTEM_MESSAGE_SET, chat.last_bot_txt())

        await user.send_message('!gpt system system message 2')
        self.assertEqual(SYSTEM_MESSAGE_SET, chat.last_bot_txt())

        actual_system_prompt = Chat.objects.get(id=chat.id).gpt_system_prompt
        self.assertEqual('system message 2', actual_system_prompt)

    async def test_each_command_without_replied_messages_is_in_its_own_context(self):
        _, user = init_chat_user()
        # 3 commands are sent. Each has context of 1 message
        for i in range(1, 4):
            mock_method = AsyncMock(return_value=MockLiteLLMResponseObject())
            with (
                mock.patch(LITELLM_ACOMPLETION, mock_method)
            ):
                prompt = f'Prompt no. {i}'
                await user.send_message(f'.gpt {prompt}')
                mock_method.assert_called_with(
                    model=test_model_name,
                    messages=single_user_message_context(prompt)
                )

    async def test_context_content(self):
        """ A little bit more complicated test. Tests that messages in reply threads are included
            in the next replies message context as expected. Here we create first a chain of
            three gpt-command that each are replies to previous commands answer from bot. Each
            bots answer is reply to the command that triggered it. So there is a continuous
            reply-chain from the first gpt-command to the last reply from bot"""
        chat, user = init_chat_user()
        await user.send_message('.gpt .system system message')
        self.assertEqual(SYSTEM_MESSAGE_SET, chat.last_bot_txt())
        prev_msg_reply = None

        # Use mock telethon client wrapper that does not try to use real library but instead a mock
        # that searches mock-objects from initiated chats bot-objects collections
        with (
            mock.patch(TELETHON_SERVICE_CLIENT, MockTelethonClientWrapper(chat.bot))
        ):
            for i in range(1, 4):
                # Send 3 messages where each message is reply to the previous one
                await user.send_message(f'.gpt message {i}', reply_to_message=prev_msg_reply)
                prev_msg_reply = chat.last_bot_msg()

            # Now that we have create a chain of 6 messages (3 commands, and 3 answers), add
            # one more reply to the chain and check, that the MockApi is called with all previous
            # messages in the context (in addition to the system message)
            mock_method = AsyncMock(return_value=MockLiteLLMResponseObject())
            with mock.patch(LITELLM_ACOMPLETION, mock_method):
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
            mock_method.assert_called_with(
                model=test_model_name,
                messages=expected_call_args_messages
            )

    async def test_no_system_message(self):
        chat, user = init_chat_user()
        mock_method = AsyncMock(return_value=MockLiteLLMResponseObject())
        with (
            mock.patch(TELETHON_SERVICE_CLIENT, MockTelethonClientWrapper(chat.bot)),
            mock.patch(LITELLM_ACOMPLETION, mock_method)
        ):
            await user.send_message('.gpt test')
            expected_call_args_messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'test'}]}]
            mock_method.assert_called_with(
                model=test_model_name,
                messages=expected_call_args_messages
            )

            # Now, if system message is added, it is included in call after that
            await user.send_message('.gpt .system system message')
            await user.send_message('.gpt test2')
            expected_call_args_messages = [
                {'role': 'system', 'content': [{'type': 'text', 'text': 'system message'}]},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'test2'}]}
            ]
            mock_method.assert_called_with(
                model=test_model_name,
                messages=expected_call_args_messages
            )

    async def test_gpt_command_without_any_message_as_reply_to_another_message(self):
        """
        Tests that if user replies to another message with just '/gpt' command, then that
        other message (and any messages in the reply chain) are included in the api calls
        context message history. The '/gpt' command message itself is not included, as it
        contains nothing else than the command itself.
        """
        chat, user = init_chat_user()
        mock_method = AsyncMock(return_value=MockLiteLLMResponseObject())
        with (
            mock.patch(TELETHON_SERVICE_CLIENT, MockTelethonClientWrapper(chat.bot)),
            mock.patch(LITELLM_ACOMPLETION, mock_method)
        ):
            original_message = await user.send_message('some message')
            gpt_command_message = await user.send_message('.gpt', reply_to_message=original_message)
            expected_call_args_messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'some message'}]}]
            mock_method.assert_called_with(
                model=test_model_name,
                messages=expected_call_args_messages
            )

            # Now, if there is just a gpt-command in the reply chain, that message is excluded from
            # the context message history for later calls
            await user.send_message('/gpt something else', reply_to_message=gpt_command_message)
            expected_call_args_messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'some message'}]},
                                           {'role': 'user', 'content': [{'type': 'text', 'text': 'something else'}]}]
            mock_method.assert_called_with(
                model=test_model_name,
                messages=expected_call_args_messages
            )

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
        mock_method = AsyncMock(return_value=MockLiteLLMResponseObject())
        with (
            mock.patch(LITELLM_ACOMPLETION, mock_method)
        ):
            chat, user = init_chat_user()
            await user.send_message('hi')  # Saves user and chat to the database
            chat_entity = Chat.objects.get(id=chat.id)
            chat_entity.quick_system_prompts = {'1': 'quick system message'}
            chat_entity.save()
            await user.send_message('/gpt /1 gpt prompt')

            expected_call_args = [{'role': 'system', 'content': [{'type': 'text', 'text': 'quick system message'}]},
                                  {'role': 'user', 'content': [{'type': 'text', 'text': 'gpt prompt'}]}]
            mock_method.assert_called_with(
                model=test_model_name,
                messages=expected_call_args
            )

    async def test_another_quick_system_prompt(self):
        mock_method = AsyncMock(return_value=MockLiteLLMResponseObject())
        with (
            mock.patch(LITELLM_ACOMPLETION, mock_method)
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
            mock_method.assert_called_with(
                model=test_model_name,
                messages=expected_messages
            )

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

    async def test_message_with_image(self):
        """
        Case where user sends a gpt command message with an image and then replies to it with another message.
        Bot should contain same base64 string for the image in both of the requests
        """
        chat, user = init_chat_user()

        mock_method = AsyncMock(return_value=MockLiteLLMResponseObject())
        mock_image_bytes = b'\0'
        mock_telethon_client = MockTelethonClientWrapper(chat.bot)
        mock_telethon_client.image_bytes_to_return = [mock_image_bytes]
        with (
            mock.patch(LITELLM_ACOMPLETION, mock_method),
            mock.patch(TELETHON_SERVICE_CLIENT, mock_telethon_client)
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
            mock_method.assert_called_with(
                model=test_model_name,
                messages=[expected_initial_message]
            )

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
            mock_method.assert_called_with(
                model=test_model_name,
                messages=expected_messages
            )

    async def test_client_response_generation_error(self):
        chat, user = init_chat_user()
        with mock.patch('bot.commands.gpt.generate_and_format_result_text', raises_response_generation_exception):
            await user.send_message('/gpt test')

        self.assertIn('response generation raised an exception', chat.last_bot_txt())

    async def test_service_unavailable_error(self):
        chat, user = init_chat_user()
        mock_method = AsyncMock(
            return_value=MockLiteLLMResponseObject(),
            side_effect=ServiceUnavailableError(message='foo', llm_provider='Some Provider', model='bar')
        )
        with (
            mock.patch(LITELLM_ACOMPLETION, mock_method)
        ):
            await user.send_message('/gpt test')

        self.assertIn('palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut.',
                      chat.last_bot_txt())

    async def test_unknown_litellm_error(self):
        chat, user = init_chat_user()

        # Simulate an unknown error (not one of the specifically handled exceptions)
        class UnknownLLMError(Exception):
            pass

        mock_method = AsyncMock(
            return_value=MockLiteLLMResponseObject(),
            side_effect=UnknownLLMError()
        )
        with (
            mock.patch(LITELLM_ACOMPLETION, mock_method)
        ):
            await user.send_message('/gpt test')

        self.assertIn('Vastauksen generointi epäonnistui.',
                      chat.last_bot_txt())

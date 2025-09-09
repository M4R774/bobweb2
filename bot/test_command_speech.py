from unittest import mock

import django
import pytest

import bot.config
from bot import main
from bot.command import ChatCommand
from bot.command_speech import SpeechCommand
from bot.tests_mocks_v2 import init_chat_user
from bot.tests_utils import assert_command_triggers, mock_openai_http_response


speech_api_mock_response_200 = mock_openai_http_response(response_bytes_body=str.encode('this is hello.mp3 in bytes'))


speech_api_mock_response_client_response_error = mock_openai_http_response(
    status=500, response_json_body={'error': {'code': 'server error', 'message': ''}})


openai_service_unavailable_error = mock_openai_http_response(
    status=503, response_json_body={'error': {'code': 'rate_limit', 'message': ''}})


openai_api_rate_limit_error = mock_openai_http_response(
    status=429, response_json_body={'error': {'code': 'billing_hard_limit_reached', 'message': ''}})


@pytest.mark.asyncio
@mock.patch('bot.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
@mock.patch('bot.async_http.post', speech_api_mock_response_200)
class SpeechCommandTest(django.test.TransactionTestCase):
    bot.config.openai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'
    command_class: ChatCommand.__class__ = SpeechCommand
    command_str: str = 'lausu'

    @classmethod
    def setUpClass(cls) -> None:
        super(SpeechCommandTest, cls).setUpClass()
        cls.maxDiff = None

    async def test_command_triggers(self):
        should_trigger = [f'/{self.command_str}', f'!{self.command_str}', f'.{self.command_str}',
                          f'/{self.command_str.upper()}', f'/{self.command_str.upper()} test']
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}']
        await assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    async def test_when_no_parameter_and_not_reply_gives_help_text(self):
        chat, user = init_chat_user()
        await user.send_message('/lausu')
        self.assertEqual('Kirjoita lausuttava viesti komennon \'\\lausu\' jälkeen '
                         'tai lausu toinen viesti vastaamalla siihen pelkällä komennolla',
                         chat.last_bot_txt())

    async def test_when_no_parameter_and_reply_with_no_to_text_gives_help_text(self):
        chat, user = init_chat_user()
        message = await user.send_message('')
        await user.send_message('/lausu', reply_to_message=message)
        self.assertEqual('Kirjoita lausuttava viesti komennon \'\\lausu\' jälkeen '
                         'tai lausu toinen viesti vastaamalla siihen pelkällä komennolla',
                         chat.last_bot_txt())

    async def test_when_ok_parameter_but_also_reply_gives_parameter_as_speech(self):
        chat, user = init_chat_user()
        message = await user.send_message('should not translate')
        await user.send_message('/lausu hello', reply_to_message=message)
        self.assertEqual('hello',
                         chat.last_bot_txt())

    async def test_too_long_title_gets_cut(self):
        chat, user = init_chat_user()
        message = await user.send_message('this is a too long prompt to be in title fully')
        await user.send_message('/lausu', reply_to_message=message)
        self.assertEqual('this is a ',
                         chat.last_bot_txt())

    async def test_client_response_error(self):
        chat, user = init_chat_user()
        message = await user.send_message('hello')
        with (
            self.assertLogs(level='ERROR') as log,
            mock.patch(
                'bot.async_http.post',
                speech_api_mock_response_client_response_error)):
            await user.send_message('/lausu', reply_to_message=message)
            self.assertIn('OpenAI API request failed. [status]: 500, [error_code]: "server error", [message]: ""',
                          log.output[-1])
            self.assertEqual(
                'Tekstin lausuminen epäonnistui.',
                chat.last_bot_txt())

    async def test_service_unavailable_error(self):
        chat, user = init_chat_user()
        message = await user.send_message('hello')
        with (
            mock.patch(
                'bot.async_http.post',
                openai_service_unavailable_error)):
            await user.send_message('/lausu', reply_to_message=message)
            self.assertEqual(
                'OpenAi:n palvelu ei ole käytettävissä '
                'tai se on juuri nyt ruuhkautunut. '
                'Ole hyvä ja yritä hetken päästä uudelleen.',
                chat.last_bot_txt())

    async def test_rate_limit_error(self):
        chat, user = init_chat_user()
        message = await user.send_message('hello')
        with (
            mock.patch(
                'bot.async_http.post',
                openai_api_rate_limit_error)):
            await user.send_message('/lausu', reply_to_message=message)
            self.assertEqual(
                'Käytettävissä oleva kiintiö on käytetty.',
                chat.last_bot_txt())

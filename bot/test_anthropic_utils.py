import anthropic
import httpx
import pytest
from django.test import TestCase
from unittest.mock import AsyncMock, patch

from bot.anthropic_utils import create_message, to_anthropic_messages, extract_text, ResponseGenerationException

ANTHROPIC_CREATE = 'anthropic.resources.messages.AsyncMessages.create'


class MockResponse:
    def __init__(self, content=None, stop_reason='end_turn'):
        self.content = content or []
        self.stop_reason = stop_reason


class MockBlock:
    def __init__(self, type_: str, text: str = ''):
        self.type = type_
        self.text = text


def api_error(error_class, status_code: int):
    request = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')
    return error_class('Some error', response=httpx.Response(status_code, request=request), body=None)


async def call():
    return await create_message(model='test-model', messages=[])


@pytest.mark.asyncio
class TestCreateMessage(TestCase):

    async def test_success(self):
        mock_response = MockResponse([MockBlock('text', 'Hello world')])
        mock_create = AsyncMock(return_value=mock_response)
        with patch(ANTHROPIC_CREATE, new=mock_create):
            result = await create_message(model='test-model', messages=[{'role': 'user', 'content': 'hi'}],
                                          system='sys', tools=[{'name': 'tool'}])
        assert result == mock_response
        mock_create.assert_called_once_with(model='test-model', messages=[{'role': 'user', 'content': 'hi'}],
                                            max_tokens=4096, system='sys', tools=[{'name': 'tool'}])

    async def test_optional_params_are_left_out_when_not_given(self):
        mock_create = AsyncMock(return_value=MockResponse())
        with patch(ANTHROPIC_CREATE, new=mock_create):
            await call()
        assert 'system' not in mock_create.call_args.kwargs
        assert 'tools' not in mock_create.call_args.kwargs

    async def test_bad_request_error(self):
        with patch(ANTHROPIC_CREATE, new=AsyncMock(side_effect=api_error(anthropic.BadRequestError, 400))):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await call()
        assert "Pyyntösi hylättiin turvajärjestelmämme seurauksena" in exc_info.value.response_text

    async def test_refusal_stop_reason(self):
        with patch(ANTHROPIC_CREATE, new=AsyncMock(return_value=MockResponse(stop_reason='refusal'))):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await call()
        assert "Pyyntösi hylättiin turvajärjestelmämme seurauksena" in exc_info.value.response_text

    async def test_authentication_error(self):
        with patch(ANTHROPIC_CREATE, new=AsyncMock(side_effect=api_error(anthropic.AuthenticationError, 401))):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await call()
        assert "Tarkista API-avaimesi" in exc_info.value.response_text

    async def test_rate_limit_error(self):
        with patch(ANTHROPIC_CREATE, new=AsyncMock(side_effect=api_error(anthropic.RateLimitError, 429))):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await call()
        assert "Palveluntarjoajan käyttöraja on saavutettu" in exc_info.value.response_text

    async def test_service_unavailable_error(self):
        with patch(ANTHROPIC_CREATE, new=AsyncMock(side_effect=api_error(anthropic.InternalServerError, 529))):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await call()
        assert "palvelu ei ole käytettävissä" in exc_info.value.response_text

    async def test_unknown_exception(self):
        class UnknownLLMError(Exception):
            pass

        with patch(ANTHROPIC_CREATE, new=AsyncMock(side_effect=UnknownLLMError("Unexpected failure"))):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await call()
        assert "Vastauksen generointi epäonnistui." in exc_info.value.response_text


class TestMessageConversion(TestCase):

    def test_system_messages_are_extracted(self):
        system, messages = to_anthropic_messages([
            {'role': 'system', 'content': [{'type': 'text', 'text': 'be nice'}]},
            {'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]},
        ])
        self.assertEqual('be nice', system)
        self.assertEqual([{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}], messages)

    def test_no_system_message(self):
        system, _ = to_anthropic_messages([{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}])
        self.assertIsNone(system)

    def test_string_content_is_converted_to_text_block(self):
        _, messages = to_anthropic_messages([{'role': 'user', 'content': 'hi'}])
        self.assertEqual([{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}], messages)

    def test_base64_image_is_converted(self):
        _, messages = to_anthropic_messages([{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,AAAA'}}]}])
        self.assertEqual([{'role': 'user', 'content': [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': 'AAAA'}}]}], messages)

    def test_url_image_is_converted(self):
        _, messages = to_anthropic_messages([{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': 'https://example.com/a.png'}}]}])
        self.assertEqual([{'role': 'user', 'content': [
            {'type': 'image', 'source': {'type': 'url', 'url': 'https://example.com/a.png'}}]}], messages)

    def test_extract_text_skips_non_text_blocks(self):
        response = MockResponse([MockBlock('text', 'a'), MockBlock('server_tool_use'), MockBlock('text', 'b')])
        self.assertEqual('ab', extract_text(response))

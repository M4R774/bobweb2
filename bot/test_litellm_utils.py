import pytest
from django.test import TestCase
from unittest.mock import AsyncMock, patch
from bot.litellm_utils import acompletion, ResponseGenerationException

from litellm import (
    ContentPolicyViolationError,
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError
)

@pytest.mark.asyncio
class TestACompletion(TestCase):

    async def test_acompletion_success(self):
        mock_response = {"choices": [{"message": {"content": "Hello world"}}]}
        with patch("bot.litellm_utils.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await acompletion("test")
            assert result == mock_response

    async def test_content_policy_violation_error(self):
        error = ContentPolicyViolationError("Some error", 403, "openai")
        with patch("bot.litellm_utils.litellm.acompletion", new=AsyncMock(side_effect=error)):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await acompletion("test")
            assert "Pyyntösi hylättiin turvajärjestelmämme seurauksena" in exc_info.value.response_text

    async def test_authentication_error(self):
        error = AuthenticationError("Some error", 403, "openai")
        with patch("bot.litellm_utils.litellm.acompletion", new=AsyncMock(side_effect=error)):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await acompletion("test")
            assert "Tarkista API-avaimesi" in exc_info.value.response_text

    async def test_rate_limit_error(self):
        error = RateLimitError("Some error", 403, "openai")
        with patch("bot.litellm_utils.litellm.acompletion", new=AsyncMock(side_effect=error)):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await acompletion("test")
            assert "Palveluntarjoajan käyttöraja on saavutettu" in exc_info.value.response_text

    async def test_service_unavailable_error(self):
        error = ServiceUnavailableError("Some error", 503, "openai")
        with patch("bot.litellm_utils.litellm.acompletion", new=AsyncMock(side_effect=error)):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await acompletion("test")
            assert "palvelu ei ole käytettävissä" in exc_info.value.response_text

    async def test_unknown_exception(self):
        # Simulate an unknown error (not one of the specifically handled exceptions)
        class UnknownLLMError(Exception):
            pass

        with patch("bot.litellm_utils.litellm.acompletion", new=AsyncMock(side_effect=UnknownLLMError("Unexpected failure"))):
            with pytest.raises(ResponseGenerationException) as exc_info:
                await acompletion("test")
            assert "Vastauksen generointi epäonnistui." in exc_info.value.response_text
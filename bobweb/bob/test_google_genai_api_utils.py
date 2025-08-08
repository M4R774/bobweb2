import os

import django
import pytest
from unittest import mock
from google import genai

import bobweb.bob.config
from bobweb.bob.google_genai_api_utils import GoogleGenaiApiSession
from bobweb.bob.litellm_utils import ResponseGenerationException

@pytest.mark.asyncio
class GoogleGenaiApiUtilsTest(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(GoogleGenaiApiUtilsTest, cls).setUpClass()
        os.system('python bobweb/web/manage.py migrate')
        bobweb.bob.config.gemini_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'

    async def test_no_env_var(self):
        bobweb.bob.config.gemini_api_key = None
        with (
            self.assertRaises(ResponseGenerationException) as context,
            self.assertLogs(level='ERROR') as log
        ):
            GoogleGenaiApiSession().get_client()
        self.assertEqual('Gemini API key is missing from environment variables', context.exception.response_text)
        self.assertIn('GEMINI_API_KEY is not set. No response was generated.', log.output[-1])

    async def test_empty_string_env_var(self):
        bobweb.bob.config.gemini_api_key = ""
        with (
            self.assertRaises(ResponseGenerationException) as context,
            self.assertLogs(level='ERROR') as log
        ):
            GoogleGenaiApiSession().get_client()
        self.assertEqual('Gemini API key is missing from environment variables', context.exception.response_text)
        self.assertIn('GEMINI_API_KEY is not set. No response was generated.', log.output[-1])

    async def test_correct_key_env_var(self):
        bobweb.bob.config.gemini_api_key = "some_correct_key"
        client = GoogleGenaiApiSession().get_client()
        assert isinstance(client, genai.Client)

    async def test_existing_client(self):
        bobweb.bob.config.gemini_api_key = "some_correct_key"
        session = GoogleGenaiApiSession()
        client = session.get_client()
        client2 = session.get_client()
        assert client == client2

    async def test_force_refresh(self):
        bobweb.bob.config.gemini_api_key = "some_correct_key"
        session = GoogleGenaiApiSession()
        client = session.get_client()
        client2 = session.get_client(force_refresh=True)
        assert client != client2

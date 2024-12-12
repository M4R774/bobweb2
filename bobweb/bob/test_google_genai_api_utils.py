import os

import django
import pytest
from unittest import mock
from google import genai

from bobweb.bob.google_genai_api_utils import GoogleGenaiApiSession
from bobweb.bob.openai_api_utils import ResponseGenerationException

@pytest.mark.asyncio
class GoogleGenaiApiUtilsTest(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(GoogleGenaiApiUtilsTest, cls).setUpClass()
        os.system('python bobweb/web/manage.py migrate')

    @mock.patch.dict(os.environ, {}, clear=True)
    async def test_no_env_var(self):
        with (
            self.assertRaises(ResponseGenerationException) as context,
            self.assertLogs(level='ERROR') as log
        ):
            GoogleGenaiApiSession().get_client()
        self.assertEqual('Google Gen AI API-avain puuttuu ympäristömuuttujista', context.exception.response_text)
        self.assertIn('GOOGLE_GENAI_API_KEY is not set. No response was generated.', log.output[-1])

    @mock.patch.dict(os.environ, {"GOOGLE_GENAI_API_KEY": ""}, clear=True)
    async def test_empty_string_env_var(self):
        with (
            self.assertRaises(ResponseGenerationException) as context,
            self.assertLogs(level='ERROR') as log
        ):
            GoogleGenaiApiSession().get_client()
        self.assertEqual('Google Gen AI API-avain puuttuu ympäristömuuttujista', context.exception.response_text)
        self.assertIn('GOOGLE_GENAI_API_KEY is not set. No response was generated.', log.output[-1])

    @mock.patch.dict(os.environ, {"GOOGLE_GENAI_API_KEY": "some_correct_key"}, clear=True)
    async def test_correct_key_env_var(self):
        client = GoogleGenaiApiSession().get_client()
        assert isinstance(client, genai.Client)

    @mock.patch.dict(os.environ, {"GOOGLE_GENAI_API_KEY": "some_correct_key"}, clear=True)
    async def test_existing_client(self):
        session = GoogleGenaiApiSession()
        client = session.get_client()
        client2 = session.get_client()
        assert client == client2

    @mock.patch.dict(os.environ, {"GOOGLE_GENAI_API_KEY": "some_correct_key"}, clear=True)
    async def test_force_refresh(self):
        session = GoogleGenaiApiSession()
        client = session.get_client()
        client2 = session.get_client(force_refresh=True)
        assert client == client2

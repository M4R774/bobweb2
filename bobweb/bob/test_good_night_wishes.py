import django
import pytest
from django.core import management
from django.test import TestCase
from unittest import mock

from bobweb.bob import main, good_night_wishes


@pytest.mark.asyncio
class GoodNighMessageTests(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(GoodNighMessageTests, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    @mock.patch('random.choice', lambda items: items[0])
    @mock.patch('random.sample', lambda items, n: items[:n])
    async def test_creating_new_good_night_message(self):
        message = await good_night_wishes.create_good_night_message()
        self.assertEqual('💤🌃 Hyvää yötä ja kauniita unia 🧸🥱', message.body)

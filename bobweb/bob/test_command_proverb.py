import datetime
import os

from django.test import TestCase

from bobweb.bob import command_proverb, database
from bobweb.bob.command_proverb import ProverbCommand
from bobweb.bob.tests_mocks_v1 import MockBot

from bobweb.bob.tests_utils import assert_command_triggers
from bobweb.web.bobapp.models import Proverb, TelegramUser, Chat


class ProverbTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(ProverbTests, cls).setUpClass()
        os.system('python bobweb/web/manage.py migrate')

    def test_command_triggers(self):
        should_trigger = ['/viisaus', '!viisaus', '.viisaus', '/viisaus test', '/VIISAUS']
        should_not_trigger = ['viisaus', 'viisaus /viisaus']
        assert_command_triggers(self, ProverbCommand, should_trigger, should_not_trigger)

    def test_create_proberb_message(self):
        mock_proverb = Proverb(proverb='Aikainen lintu madon nappaa',
                               tg_user=TelegramUser(id=1337),
                               date_created=datetime.datetime.now())
        message_txt = command_proverb.create_proverb_message(mock_proverb)
        self.assertEqual(message_txt, 'Aikainen lintu madon nappaa - 1337 ' +
                         datetime.datetime.now().strftime("%d.%m.%Y"))

    async def test_broadcast_proverb(self):
        TelegramUser.objects.all().delete()
        TelegramUser(id=420, username='Shrek').save()
        Chat(proverb_enabled=True).save()
        Proverb.objects.all().delete()
        mock_proverb = Proverb(proverb='Aikainen lintu madon nappaa',
                               tg_user=database.get_telegram_user(420),
                               date_created=datetime.datetime.now())
        mock_proverb.save()
        mock_bot = MockBot()
        await command_proverb.broadcast_proverb(mock_bot)
        self.assertEqual(mock_bot.latest_message, 'Aikainen lintu madon nappaa - Shrek ' +
                         datetime.datetime.now().strftime("%d.%m.%Y"))

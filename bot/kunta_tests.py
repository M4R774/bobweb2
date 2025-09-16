from unittest import IsolatedAsyncioTestCase

from django.core import management

from bot.commands.kunta import KuntaCommand
from bot.tests_utils import assert_command_triggers, assert_reply_to_contain


class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/kunta', '!kunta', '.kunta', '/KUNTA', '/kunta test']
        should_not_trigger = ['kunta', 'test /kunta']
        await assert_command_triggers(self, KuntaCommand, should_trigger, should_not_trigger)

    async def test_informs_that_municipality_command_is_no_longer_supported(self):
        await assert_reply_to_contain(self, '/kunta', [KuntaCommand._functionality_has_been_removed_info])

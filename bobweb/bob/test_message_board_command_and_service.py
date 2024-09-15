from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase
from telegram.ext import Application

from bobweb.bob import main, message_board_service
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_message_board import MessageBoardCommand
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockBot
from bobweb.bob.tests_utils import assert_command_triggers


@pytest.mark.asyncio
class MessageBoardCommandTests(django.test.TransactionTestCase):
    command_class: ChatCommand.__class__ = MessageBoardCommand
    command_str: str = 'ilmoitustaulu'
    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardCommandTests, cls).setUpClass()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = [
            '/ilmoitustaulu',
            '!ilmoitustaulu',
            '.ilmoitustaulu',
            '/ilmoitustaulu'.upper(),
        ]
        should_not_trigger = [
            'ilmoitustaulu',
            'test /ilmoitustaulu',
            '/ilmoitustaulu test',
        ]
        await assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)


@pytest.mark.asyncio
class MessageBoardService(django.test.TransactionTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardService, cls).setUpClass()
        management.call_command('migrate')

    async def test_service_startup(self):
        # Create on chat with message board
        chat, user = init_chat_user()
        initialize_message_board_service(bot=chat.bot)
        await user.send_message('/ilmoitustaulu')


def initialize_message_board_service(bot: 'MockBot'):
    mock_application = mock.Mock(spec=Application)
    mock_application.bot = bot

    message_board_service.instance = message_board_service.MessageBoardService(mock_application)

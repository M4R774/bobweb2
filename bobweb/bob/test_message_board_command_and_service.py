from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase
from telegram.ext import Application

from bobweb.bob import main, message_board_service, database
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_message_board import MessageBoardCommand
from bobweb.bob.message_board import MessageBoardMessage, MessageBoard
from bobweb.bob.message_board_service import create_schedule_with_chat_context
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockBot
from bobweb.bob.tests_utils import assert_command_triggers


async def mock_scheduled_message_provider(message_board: MessageBoard, _: int) -> MessageBoardMessage:
    return MessageBoardMessage(message_board=message_board, message='mock_message', preview='mock_preview')


@pytest.mark.asyncio
class MessageBoardCommandTests(django.test.TransactionTestCase):
    command_class: ChatCommand.__class__ = MessageBoardCommand
    mock_schedule = [create_schedule_with_chat_context(00, 00, mock_scheduled_message_provider)]

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardCommandTests, cls).setUpClass()
        management.call_command('migrate')

        message_board_service.default_daily_schedule = cls.mock_schedule
        message_board_service.thursday_schedule = cls.mock_schedule

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

    async def test_service_startup(self):
        # Create on chat with message board
        chat, user = init_chat_user()
        await user.send_message('hi')

        # First check that there is no message board for the chat
        chat_from_db = database.get_chat(chat.id)
        self.assertIsNone(chat_from_db.message_board_msg_id)

        initialize_message_board_service(bot=chat.bot)
        await user.send_message('/ilmoitustaulu')

        self.assertIn('mock_message', chat.last_bot_txt())
        # Now there should be a message board set for the chat
        chat_from_db = database.get_chat(chat.id)
        self.assertEqual(chat.last_bot_msg().id, chat_from_db.message_board_msg_id)

    async def test_message_board_host_message_has_been_deleted(self):
        # Create on chat with message board
        chat, user = init_chat_user()

        # Set fake message board message id for the chat and initialize service
        chat_from_db = database.get_chat(chat.id)
        chat_from_db.message_board_msg_id = -1
        chat_from_db.save()
        initialize_message_board_service(bot=chat.bot)

        # Now when the user tries to repin message board, no message exists with the currently set id. An error is
        # raised by Telegram API, but it is ignored and new message board created, as the user requests new one.
        await user.send_message('/ilmoitustaulu')
        self.assertIn('mock_message', chat.last_bot_txt())
        # Now the save id has been updated with the new one
        self.assertEqual(chat.last_bot_msg().id, database.get_chat(chat.id).message_board_msg_id)



@pytest.mark.asyncio
class MessageBoardService(django.test.TransactionTestCase):
    mock_schedule = [create_schedule_with_chat_context(00, 00, mock_scheduled_message_provider)]

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardService, cls).setUpClass()
        management.call_command('migrate')

        message_board_service.default_daily_schedule = cls.mock_schedule
        message_board_service.thursday_schedule = cls.mock_schedule

    async def test_message_board_host_message_is_deleted_while_board_is_active(self):
        # Create on chat with message board
        chat, user = init_chat_user()
        initialize_message_board_service(bot=chat.bot)

        chat_from_db = database.get_chat(chat.id)
        self.assertIsNone(chat_from_db.message_board_msg_id)

        await user.send_message('/ilmoitustaulu')

        chat_from_db = database.get_chat(chat.id)
        self.assertEqual(chat.last_bot_msg().id, chat_from_db.message_board_msg_id)

        # Find created message board and delete its host message. Then update the board
        message_board = message_board_service.find_board(chat.id)
        await chat.bot.delete_message(chat.id, message_board.host_message_id)

        await message_board.update_scheduled_message_content()
        # Now board is deleted from the service and the message board message id is set null in database
        self.assertIsNone(message_board_service.find_board(chat.id))
        self.assertIsNone(database.get_chat(chat.id).message_board_msg_id)


def initialize_message_board_service(bot: 'MockBot'):
    mock_application = mock.Mock(spec=Application)
    mock_application.bot = bot

    message_board_service.instance = message_board_service.MessageBoardService(mock_application)

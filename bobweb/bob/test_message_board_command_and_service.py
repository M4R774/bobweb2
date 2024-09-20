import datetime
from unittest import mock

import django
import pytest
from django.core import management
from django.test import TestCase
from freezegun import freeze_time
from telegram.ext import Application

from bobweb.bob import main, message_board_service, database
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_message_board import MessageBoardCommand, message_board_bad_parameter_help
from bobweb.bob.message_board import MessageBoardMessage, MessageBoard
from bobweb.bob.message_board_service import create_schedule_with_chat_context, create_schedule, \
    find_current_and_next_scheduling
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockBot
from bobweb.bob.tests_utils import assert_command_triggers


def mock_provider_provider(scheduled_message_content: str = 'mock_message'):
    async def internal(message_board: MessageBoard, _: int) -> MessageBoardMessage:
        return MessageBoardMessage(message_board=message_board, message=scheduled_message_content)
    return internal


def create_mock_schedule():
    """ Creates mock schedule that contains 3 message providers for each day of the week. """
    async def message_provider(message_board: MessageBoard, _: int) -> MessageBoardMessage:
        week_day_ordinal = datetime.datetime.now().weekday()
        time = datetime.datetime.now().strftime('%H:%M')
        return MessageBoardMessage(message_board=message_board, message=f'{week_day_ordinal} at {time}')

    daily_schedule = []
    for _, value, in enumerate([9, 12, 15]):
        schedule = create_schedule_with_chat_context(value, 00, message_provider)
        daily_schedule.append(schedule)

    return {k: daily_schedule for k in range(7)}


mock_schedule = [create_schedule_with_chat_context(00, 00, mock_provider_provider())]


@pytest.mark.asyncio
class MessageBoardCommandTests(django.test.TransactionTestCase):
    command_class: ChatCommand.__class__ = MessageBoardCommand

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardCommandTests, cls).setUpClass()
        management.call_command('migrate')

        message_board_service.default_daily_schedule = mock_schedule
        message_board_service.thursday_schedule = mock_schedule

    async def test_command_triggers(self):
        should_trigger = [
            '/ilmoitustaulu',
            '!ilmoitustaulu',
            '.ilmoitustaulu',
            '/ilmoitustaulu'.upper(),
            '.ilmoitustaulu off',
            '.ilmoitustaulu test',
        ]
        should_not_trigger = [
            'ilmoitustaulu',
            'test /ilmoitustaulu',
        ]
        await assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    async def test_command_creates_new_board(self):
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

    async def test_command_with_wrong_parameter_gives_help_text(self):
        chat, user = init_chat_user()
        await user.send_message('/ilmoitustaulu test')
        # Check that the help text is shown (just part of it is tested)
        self.assertEqual(message_board_bad_parameter_help, chat.last_bot_txt())

    async def test_command_with_off_parameter_removes_the_board(self):
        chat, user = init_chat_user()
        initialize_message_board_service(bot=chat.bot)
        await user.send_message('/ilmoitustaulu')

        chat_from_db = database.get_chat(chat.id)
        self.assertEqual(chat.last_bot_msg().id, chat_from_db.message_board_msg_id)
        self.assertIsNotNone(message_board_service.find_board(chat.id))

        await user.send_message('/ilmoitustaulu off')
        self.assertEqual('Ilmoitustaulu poistettu käytöstä', chat.last_bot_txt())

        chat_from_db = database.get_chat(chat.id)
        self.assertIsNone(chat_from_db.message_board_msg_id)
        self.assertIsNone(message_board_service.find_board(chat.id))

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
    mock_schedule = [create_schedule_with_chat_context(00, 00, mock_provider_provider())]

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardService, cls).setUpClass()
        management.call_command('migrate')

        message_board_service.default_daily_schedule = cls.mock_schedule
        message_board_service.thursday_schedule = cls.mock_schedule

    #
    # Base service
    #
    async def test_when_message_board_service_is_started_host_message_is_updated_with_the_scheduled_message(self):
        # Demonstrate that when the service starts, message set as the host message for the chat is updated with
        # the correct scheduled message. For the sake of this test and demonstration, the board host message id is
        # inserted to the database manually without using the command.
        chat, user = init_chat_user()
        await user.send_message('/ilmoitustaulu test')
        self.assertEqual(message_board_bad_parameter_help, chat.last_bot_txt())

        chat_from_db = database.get_chat(chat.id)
        chat_from_db.message_board_msg_id = chat.last_bot_msg().id
        chat_from_db.save()

        # Now as the service is started, the initial message is overridden with the mock scheduled message
        initialize_message_board_service(bot=chat.bot)
        await message_board_service.instance.update_boards_and_schedule_next_update()

        self.assertIn('mock_message', chat.last_bot_txt())

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

    async def test_find_current_and_next_scheduling(self):
        """ Create fake schedule. Check that the current and the next schedule are determined correctly in each case """
        # Setup: Create dict of schedules for each day of the week where just the week day ordinal number
        # and time is printed.
        daily_schedule = [
            create_schedule_with_chat_context(9, 00, None),
            create_schedule_with_chat_context(21, 00, None)
        ]
        schedules_by_weed_day = {i: daily_schedule for i in range(7)}

        # Now, with frozen time (1.1.2025 is wednesday)
        with freeze_time('2025-01-01 00:00') as clock:
            current_scheduling, next_scheduling = find_current_and_next_scheduling(schedules_by_weed_day)
            # Now as the time is at midnight, current schedule should be from the previous day that started
            # at 15:00. Next schedule starts today at 9:00
            self.assertEqual(21, current_scheduling.starting_from.hour)
            self.assertEqual(9, next_scheduling.starting_from.hour)

            # If we progress time to 10:00, now current schedule started at 9:00 and next starts at 15:00
            clock.tick(datetime.timedelta(hours=10))
            current_scheduling, next_scheduling = find_current_and_next_scheduling(schedules_by_weed_day)
            self.assertEqual(9, current_scheduling.starting_from.hour)
            self.assertEqual(21, next_scheduling.starting_from.hour)

            # And another tick of 12 hours and current schedule is from current date and the next schedules is from the
            # next date
            clock.tick(datetime.timedelta(hours=12))
            current_scheduling, next_scheduling = find_current_and_next_scheduling(schedules_by_weed_day)
            self.assertEqual(21, current_scheduling.starting_from.hour)
            self.assertEqual(9, next_scheduling.starting_from.hour)


def initialize_message_board_service(bot: 'MockBot'):
    mock_application = mock.Mock(spec=Application)
    mock_application.bot = bot

    message_board_service.instance = message_board_service.MessageBoardService(mock_application)

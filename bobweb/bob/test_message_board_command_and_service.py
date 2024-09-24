import asyncio
import datetime
from typing import Tuple
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
from bobweb.bob.message_board import MessageBoardMessage, MessageBoard, EventMessage
from bobweb.bob.message_board_service import create_schedule_with_chat_context, create_schedule, \
    find_current_and_next_scheduling
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockBot, MockChat, MockUser
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


def initialize_message_board_service(bot: 'MockBot'):
    mock_application = mock.Mock(spec=Application)
    mock_application.bot = bot

    message_board_service.instance = message_board_service.MessageBoardService(mock_application)


async def setup_service_and_create_board() -> Tuple[MockChat, MockUser, MessageBoard]:
    chat, user = init_chat_user()
    initialize_message_board_service(bot=chat.bot)
    await user.send_message('/ilmoitustaulu')
    return chat, user, message_board_service.find_board(chat.id)


def end_all_message_board_background_task():
    """ Makes sure, that no background update task is left running into the
        message board that is created during the tests. Also, ends all task
        right after all statements of the test method are ran. """
    if (not message_board_service
            or not message_board_service.instance
            or not message_board_service.instance.boards):
        return

    for board in message_board_service.instance.boards:
        if board._scheduled_message:
            board._scheduled_message.end_schedule()
        if board._event_update_task and asyncio.isfuture(board._event_update_task):
            board._event_update_task.cancel()
        if board._notification_update_task and asyncio.isfuture(board._notification_update_task):
            board._notification_update_task.cancel()
    message_board_service.instance.boards = []


mock_schedule = [create_schedule_with_chat_context(00, 00, mock_provider_provider())]
mock_schedules_by_week_day = {k: mock_schedule for k in range(7)}


@pytest.mark.asyncio
class MessageBoardCommandTests(django.test.TransactionTestCase):
    """ Tests MessageBoard command """
    command_class: ChatCommand.__class__ = MessageBoardCommand

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardCommandTests, cls).setUpClass()
        management.call_command('migrate')
        message_board_service.schedules_by_week_day = mock_schedules_by_week_day

    def tearDown(self):
        super().tearDown()
        end_all_message_board_background_task()

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
class MessageBoardServiceTests(django.test.TransactionTestCase):
    """ Tests MessageBoard service """

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardServiceTests, cls).setUpClass()
        management.call_command('migrate')
        message_board_service.schedules_by_week_day = mock_schedules_by_week_day

    def tearDown(self):
        super().tearDown()
        end_all_message_board_background_task()

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
        # Setup: Create dict of schedules for each day of the week when just the week day ordinal number
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


"""
Few constants for timing the tests. These are needed as the message board uses its own scheduling when there
are event or notification messages. For testing, the basic idea is to offset schedule of the test logic by 
half a tick in regards to the schedule of the tested message board.
Example:
- [  FT  ]  Full tick in test logic 
- [HT]      Half tick in test logic
- [  BT  ]  Tick in message board logic
- each pipe character is a point where operation is done (test assertion, adding new message to board etc.)

Example graph
    Test logic: [ setup, creating board etc] |[HT]|[  FT  ]|[  FT  ]|.....| TEST ENDED     |
    Board logic                              |[  BT  ]|[  BT  ]|[  BT  ]..| TASK CANCELLED |
    
This way state of the board (or contents of the host message) can be inspected in the seams where the board
logic is sleeping and waiting for the next scheduled. As this is not exact and the test logic as well as the
operations invoked in the message board take some time to execute, these tests might become flaky. Another
problem is, that it is hard to debug the tests, as stopping at a breakpoint in the test logic does not stop
the board update loop in the background which can cause discrepancy in the timings.
If there is a more robust easy to use solution for this, feel free to fix!
"""
FULL_TICK = 0.0001  # Seconds
HALF_TICK = FULL_TICK / 2


@pytest.mark.asyncio
class MessageBoardTests(django.test.TransactionTestCase):
    """ Tests MessageBoard class itself. As the board is updated with a background task that updates the
        state of the message board, delays are used here. Hence, this test class might run a bit slower than
        the others.

        NOTE! As these tests relay on asyncio.sleep() AND are testing background scheduled tasks, using debug with
        breakpoint(s) might yield different result than running the tests without debugger.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardTests, cls).setUpClass()
        management.call_command('migrate')
        message_board_service.schedules_by_week_day = mock_schedules_by_week_day
        # Delay of the board updates are set to be one full tick.
        MessageBoard._board_event_update_interval_in_seconds = FULL_TICK

    def tearDown(self):
        super().tearDown()
        end_all_message_board_background_task()

    async def test_set_new_scheduled_message(self):
        """ When scheduled message is added, it is updated to the board IF there is no event message loop running.
            If event message loop is running, the board loops through all events and the scheduled message. """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('mock_message', chat.last_bot_txt())

        msg_1 = MessageBoardMessage(board, '1')
        await board.set_new_scheduled_message(msg_1)
        self.assertEqual('1', chat.last_bot_txt())

        # When new scheduled message is added, previous is set to be ending
        self.assertEqual(False, msg_1.schedule_set_to_end)
        msg_2 = MessageBoardMessage(board, '2')
        await board.set_new_scheduled_message(msg_2)
        self.assertEqual('2', chat.last_bot_txt())
        # Now previous scheduled message has been set as ended
        self.assertEqual(True, msg_1.schedule_set_to_end)

        # If there is an active event update loop, the scheduled message is not updated immediately to the board
        event = EventMessage(board, 'event', -1)
        board.add_event_message(event)

        # Now the event has been updated to the board
        await asyncio.sleep(HALF_TICK)  # Offset tests timing with a half a tick with regarding the update task schedule
        self.assertEqual('event', chat.last_bot_txt())

        await asyncio.sleep(FULL_TICK)  # Wait for one tick
        self.assertEqual('2', chat.last_bot_txt())  # Now the board has been rotated to the normal scheduled message

        await asyncio.sleep(FULL_TICK)  # Again, one tick
        self.assertEqual('event', chat.last_bot_txt())  # Back at the event

        # Now, as the last step test, that if there is a event loop running, new scheduled message content is not
        # updated immediately to the board, but only when it's turn comes in the loop.
        # Wait until has rotated back to the scheduled message

        await asyncio.sleep(FULL_TICK)
        self.assertEqual('2', chat.last_bot_txt())

        # Change scheduled message.
        msg_3 = MessageBoardMessage(board, '3')
        await board.set_new_scheduled_message(msg_3)

        # Wait half a tick, the board still has the previous scheduled message
        self.assertEqual('2', chat.last_bot_txt())

        # After another half a tick, it has changed to the event message
        await asyncio.sleep(FULL_TICK)
        self.assertEqual('event', chat.last_bot_txt())

        # And after one full tick, new scheduled message is shown
        await asyncio.sleep(FULL_TICK)
        self.assertEqual('3', chat.last_bot_txt())

    async def test_update_scheduled_message_content(self):
        """ When called without a parameter, current scheduled messages content is updated
            to the message in the chat. So as a scheduled message updates state of itself, it is reflected in
            Telegram only if the message is edited. This method causes Telegram API-call that edits contents of
            the message that hosts the message board. """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('mock_message', chat.last_bot_txt())

        msg_1 = MessageBoardMessage(board, '1')
        await board.set_new_scheduled_message(msg_1)

        # Now content of the message is edited
        msg_1.message = '1 (edited)'
        await msg_1.message_board.update_scheduled_message_content()
        self.assertEqual('1 (edited)', chat.last_bot_txt())

        # The content is not updated immediately, if there is an event loop running
        event = EventMessage(board, 'event', -1)
        board.add_event_message(event)
        await asyncio.sleep(HALF_TICK)  # Offset with boards update schedule
        self.assertEqual('event', chat.last_bot_txt())

        # Now if the message is updated, it's updated content is shown on the board only after it is shceuled messages
        # turn in the update loop
        msg_1.message = '1 (edited 2)'
        await msg_1.message_board.update_scheduled_message_content()
        self.assertEqual('event', chat.last_bot_txt())

        # Now after a tick, the updated scheduled message is found from the board
        await asyncio.sleep(HALF_TICK)
        self.assertEqual('1 (edited 2)', chat.last_bot_txt())



import asyncio
import datetime
import logging
from typing import Tuple
from unittest import mock
from unittest.mock import Mock

import django
import pytest
import telegram.error
from django.core import management
from django.test import TestCase
from freezegun import freeze_time
from telegram.ext import Application, CallbackContext

from bobweb.bob import main, message_board_service, database, command_message_board, config
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_message_board import MessageBoardCommand, message_board_bad_parameter_help
from bobweb.bob.message_board import MessageBoardMessage, MessageBoard, EventMessage, NotificationMessage
from bobweb.bob.message_board_service import create_schedule_with_chat_context, create_schedule, \
    find_current_and_next_scheduling
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockBot, MockChat, MockUser
from bobweb.bob.tests_utils import assert_command_triggers, AsyncMock

logging.getLogger().setLevel(logging.DEBUG)


def mock_provider_provider(scheduled_message_content: str = 'scheduled_message'):
    async def internal(message_board: MessageBoard, _: int) -> MessageBoardMessage:
        return MessageBoardMessage(message_board=message_board, message=scheduled_message_content)
    return internal


async def mock_pin_and_unpin_raises_exception(*args, **kwargs):
    raise telegram.error.BadRequest(command_message_board.tg_no_rights_to_pin_or_unpin_messages_error)


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

        self.assertIn('scheduled_message', chat.last_bot_txt())
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
        self.assertIn('scheduled_message', chat.last_bot_txt())
        # Now the save id has been updated with the new one
        self.assertEqual(chat.last_bot_msg().id, database.get_chat(chat.id).message_board_msg_id)

    async def test_message_board_bot_has_no_rights_to_pin_messages(self):
        # Create on chat with message board and change its pin and unpin methods to mock ones that raises exception
        chat, user = init_chat_user()

        mock_application = Mock(spec=Application)
        mock_application.bot = chat.bot
        chat.bot.pin_chat_message = mock_pin_and_unpin_raises_exception

        # No error is thrown and user is given a notification that informs that the bot should be given pin management
        # rights in the chat
        await user.send_message('/ilmoitustaulu', context=CallbackContext(application=mock_application))
        self.assertEqual(command_message_board.no_pin_rights_notification, chat.last_bot_txt())


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

        self.assertIn('scheduled_message', chat.last_bot_txt())

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
FULL_TICK = 0.005  # Seconds
HALF_TICK = FULL_TICK / 2


@pytest.mark.asyncio
class MessageBoardTests(django.test.TransactionTestCase):
    """ Tests MessageBoard class itself. As the board is updated with a background task that updates the
        state of the message board, delays are used here. Hence, this test class might run a bit slower than
        the others.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super(MessageBoardTests, cls).setUpClass()
        management.call_command('migrate')
        message_board_service.schedules_by_week_day = mock_schedules_by_week_day
        # Delay of the board updates are set to be one full tick.
        MessageBoard._board_event_update_interval_in_seconds = FULL_TICK
        NotificationMessage._board_notification_update_interval_in_seconds = FULL_TICK

    def tearDown(self):
        super().tearDown()
        end_all_message_board_background_task()
        MessageBoard._board_event_update_interval_in_seconds = FULL_TICK
        NotificationMessage._board_notification_update_interval_in_seconds = FULL_TICK

    async def test_set_new_scheduled_message(self):
        """ When scheduled message is added, it is updated to the board IF there is no event message loop running.
            If event message loop is running, the board loops through all events and the scheduled message. """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

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
        await board.proceed_current_update_loop()
        self.assertEqual('event', chat.last_bot_txt())

        await board.proceed_current_update_loop()
        self.assertEqual('2', chat.last_bot_txt())  # Now the board has been rotated to the normal scheduled message

        await board.proceed_current_update_loop()
        self.assertEqual('event', chat.last_bot_txt())  # Back at the event

        # Now, as the last step test, that if there is a event loop running, new scheduled message content is not
        # updated immediately to the board, but only when it's turn comes in the loop.
        # Wait until has rotated back to the scheduled message

        await board.proceed_current_update_loop()
        self.assertEqual('2', chat.last_bot_txt())

        # Change scheduled message.
        msg_3 = MessageBoardMessage(board, '3')
        await board.set_new_scheduled_message(msg_3)

        # Wait half a tick, the board still has the previous scheduled message
        self.assertEqual('2', chat.last_bot_txt())

        # After another half a tick, it has changed to the event message
        await board.proceed_current_update_loop()
        self.assertEqual('event', chat.last_bot_txt())

        # And after one full tick, new scheduled message is shown
        await board.proceed_current_update_loop()
        self.assertEqual('3', chat.last_bot_txt())

    async def test_update_scheduled_message_content(self):
        """ When called without a parameter, current scheduled messages content is updated
            to the message in the chat. So as a scheduled message updates state of itself, it is reflected in
            Telegram only if the message is edited. This method causes Telegram API-call that edits contents of
            the message that hosts the message board. """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

        msg_1 = MessageBoardMessage(board, '1')
        await board.set_new_scheduled_message(msg_1)

        # Now content of the message is edited
        msg_1.message = '1 (edited)'
        await board.update_scheduled_message_content()
        self.assertEqual('1 (edited)', chat.last_bot_txt())

        # The content is not updated immediately, if there is an event loop running
        event = EventMessage(board, 'event', -1)
        board.add_event_message(event)
        await board.proceed_current_update_loop()
        self.assertEqual('event', chat.last_bot_txt())

        # Now if the message is updated, it's updated content is shown on the board only after it is scheduled messages
        # turn in the update loop
        msg_1.message = '1 (edited 2)'
        await board.update_scheduled_message_content()
        self.assertEqual('event', chat.last_bot_txt())

        # Now after a tick, the updated scheduled message is found from the board
        await board.proceed_current_update_loop()
        self.assertEqual('1 (edited 2)', chat.last_bot_txt())

    async def test_add_event_message(self):
        """ When event message is added to the board, if there is no active event message rotation loop task running
            new one is started. The board loops all event messages and current scheduled message in the board. When
            new event messages are added, they are shown when its their time in the loop. """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('scheduled_message', chat.last_bot_txt())
        self.assertEqual(0, len(board._event_messages))

        # Add event. Check that it and the scheduled message are rotated.
        event = EventMessage(board, 'event')
        board.add_event_message(event)
        await board.proceed_current_update_loop()
        self.assertEqual('event', chat.last_bot_txt())
        self.assertEqual(1, len(board._event_messages))
        await board.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

        # Now add new event message. It is shown when it's turn comes next
        event_2 = EventMessage(board, 'event_2')
        board.add_event_message(event_2)

        # Added event has not yet been updated to the board
        await board.proceed_current_update_loop()
        self.assertEqual('event', chat.last_bot_txt())

        # Now the new event is shown when its turn comes in the rotation
        await board.proceed_current_update_loop()
        self.assertEqual('event_2', chat.last_bot_txt())
        self.assertEqual(2, len(board._event_messages))

        # And next the scheduled message is shown again
        await board.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

    async def test_remove_event_message(self):
        """ When event is removed by MessageBoardMessage id or events original_activity_message_id, it is expected
            to be removed from the board. If the event message is currently being shown on the board, it is not
            immediately switched to a new event but only after normal board rotation """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('scheduled_message', chat.last_bot_txt())
        self.assertEqual(0, len(board._event_messages))

        # Add event. Check that it and the scheduled message are rotated.
        event = EventMessage(board, 'event')
        board.add_event_message(event)
        await board.proceed_current_update_loop()
        self.assertEqual('event', chat.last_bot_txt())
        self.assertEqual(1, len(board._event_messages))

        # Remove the event - expected to be removed BUT the message board contains the event until it is updated
        was_removed = board.remove_event_by_id(event.id)
        self.assertEqual(True, was_removed)
        self.assertEqual(0, len(board._event_messages))
        self.assertEqual('event', chat.last_bot_txt())

        await board.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

        # Now add new event that has original_activity_message_id
        event_with_msg_id = EventMessage(board, 'event_with_msg_id', original_activity_message_id=123)
        board.add_event_message(event_with_msg_id)
        await board.proceed_current_update_loop()
        self.assertEqual('event_with_msg_id', chat.last_bot_txt())
        self.assertEqual(1, len(board._event_messages))

        # Remove message with id
        was_removed = board.remove_event_by_message_id(event_with_msg_id.original_activity_message_id)
        self.assertEqual(True, was_removed)
        self.assertEqual(0, len(board._event_messages))
        self.assertEqual('event_with_msg_id', chat.last_bot_txt())

        # After one tick, scheduled message is shown again
        await board.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

    async def test_add_notification(self):
        """ When notification is added, it is added the notification queue. If there are notifications and an active
            notification update loop, the new notification is shown when its turn comes in the queue. If there is no
            active notification update loop, new one is created, and it is run until notification queue is empty.
            Displaying notifications halts current event update loop until notification loop has ended. """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('scheduled_message', chat.last_bot_txt())
        self.assertEqual(0, len(board._notification_queue))

        # Add notifications, wait half a tick and check that the notification is shown
        notification = NotificationMessage(board, '1')
        board.add_notification(notification)
        # Notification is found from the list until it is consumed and added to the board
        self.assertEqual(1, len(board._notification_queue))
        await board.proceed_current_update_loop()
        # Now the notification has been updated to the board and removed from the queue
        self.assertEqual('1', chat.last_bot_txt())
        self.assertEqual(0, len(board._notification_queue))

        # After notification delay, scheduled message is shown again
        await board.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

    async def test_add_notification_multiple_notifications(self):
        """ Multiple notifications can be added. Each one added to the queue is shown on the same order """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('scheduled_message', chat.last_bot_txt())
        self.assertEqual(0, len(board._notification_queue))

        # Add notifications, wait half a tick and check that the notification is shown
        notification_1 = NotificationMessage(board, '1')
        notification_2 = NotificationMessage(board, '2')
        board.add_notification(notification_1)
        board.add_notification(notification_2)
        self.assertEqual(2, len(board._notification_queue))

        await board.proceed_current_update_loop()
        # Now the notification has been updated to the board and removed from the queue
        self.assertEqual('1', chat.last_bot_txt())
        self.assertEqual(1, len(board._notification_queue))

        await board.proceed_current_update_loop()
        self.assertEqual('2', chat.last_bot_txt())
        self.assertEqual(0, len(board._notification_queue))

        await board.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

    async def test_add_notification_when_event_loop_is_active(self):
        """ Displaying notifications halts current event update loop until notification loop has ended. """
        chat, user, board = await setup_service_and_create_board()
        self.assertEqual('scheduled_message', chat.last_bot_txt())
        self.assertEqual(0, len(board._event_messages))

        # Add event. Check that it and the scheduled message are rotated.
        event = EventMessage(board, 'event')
        board.add_event_message(event)
        # Offset with boards update schedule. In this test, the offset is 1 full tick
        # as double as the event update schedule takes 2 full ticks
        await board.proceed_current_update_loop()

        # Add notification and check that it is shown. After the notification,
        # the event should be updated back to the board
        notification = NotificationMessage(board, 'notification')
        board.add_notification(notification)

        await board.proceed_current_update_loop()
        self.assertEqual('notification', chat.last_bot_txt())

        # Now, after one tick, the event should be back on the board
        await board.proceed_current_update_loop()
        self.assertEqual('event', chat.last_bot_txt())

        # After another tick the event loop has updated scheduled message to the board
        await board.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

        # Now if we add a new notification to the board, it is again shown for a tick
        notification_2 = NotificationMessage(board, 'notification_2')
        board.add_notification(notification_2)
        await board.proceed_current_update_loop()
        self.assertEqual('notification_2', chat.last_bot_txt())

        # And after a tick, the scheduled_message is again shown on the board
        await board.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat.last_bot_txt())

    async def test_multiple_chats_and_multiple_boards(self):
        """ Show that message boards are chat specific and independent of each other. """
        chat_1, _, board_1 = await setup_service_and_create_board()
        chat_2, _, board_2 = await setup_service_and_create_board()

        self.assertEqual('scheduled_message', chat_1.last_bot_txt())
        self.assertEqual('scheduled_message', chat_2.last_bot_txt())

        # Now event is added to the board one
        event = EventMessage(board_1, 'event')
        board_1.add_event_message(event)

        await board_1.proceed_current_update_loop()
        await board_2.proceed_current_update_loop()
        self.assertEqual('event', chat_1.last_bot_txt())
        self.assertEqual('scheduled_message', chat_2.last_bot_txt())

        await board_1.proceed_current_update_loop()
        await board_2.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat_1.last_bot_txt())
        self.assertEqual('scheduled_message', chat_2.last_bot_txt())

        # Add notification to board 2
        notification = NotificationMessage(board_2, 'notification')
        board_2.add_notification(notification)

        # Board 1 has rotated back to the event message, board 2 shows the notification
        await board_1.proceed_current_update_loop()
        await board_2.proceed_current_update_loop()
        self.assertEqual('event', chat_1.last_bot_txt())
        self.assertEqual('notification', chat_2.last_bot_txt())

        await board_1.proceed_current_update_loop()
        await board_2.proceed_current_update_loop()
        self.assertEqual('scheduled_message', chat_1.last_bot_txt())
        self.assertEqual('scheduled_message', chat_2.last_bot_txt())

    async def test__find_next_event(self):
        """ Tests internal implementation to make sure that it works as expected. This uses hidden attributes
            and methods. Feel free to discard this text if implementation changes too much or this slows development """
        chat, user, board = await setup_service_and_create_board()

        # When there are no events (when las event has been removed)
        self.assertEqual(None, board._current_event_id)
        self.assertEqual(None, board._find_next_event())

        # When has one event and no current_event_id is set (for example when fist event is added)
        event_1 = EventMessage(board, '1')
        # Normal list append is used instead of ´add_event_message()´ as we don't want to have update
        # loop in the background
        board._event_messages.append(event_1)

        self.assertEqual(None, board._current_event_id)
        self.assertEqual(event_1, board._find_next_event())

        # Simulate, that the event is set as the current event to the board. Now None is returned to set scheduled
        # message to the board for one iteration of the rotation
        board._current_event_id = event_1.id
        actual = board._find_next_event()
        self.assertEqual(None, actual)
        board._current_event_id = None

        # Add few more events
        event_2 = EventMessage(board, '2')
        board._event_messages.append(event_2)
        event_3 = EventMessage(board, '3')
        board._event_messages.append(event_3)

        # Now we can rotate through the events until after the last one None is returned. After each, previous returned
        # value is set as the current event id to simulate ro
        actual = board._find_next_event()
        self.assertEqual(event_1, actual)

        board._current_event_id = actual.id
        actual = board._find_next_event()
        self.assertEqual(event_2, actual)

        board._current_event_id = actual.id
        actual = board._find_next_event()
        self.assertEqual(event_3, actual)

        board._current_event_id = actual.id
        actual = board._find_next_event()
        self.assertEqual(None, actual)

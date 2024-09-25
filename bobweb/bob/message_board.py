import asyncio
import itertools
import logging
from typing import List, Tuple, Generator

import telegram
from telegram.constants import ParseMode

from bobweb.bob.utils_common import handle_exception

logger = logging.getLogger(__name__)

"""
Message board can have three types of message:s notifications, events and scheduled messages.

Notifications: short messages that are shown for a given short duration_in_seconds.
If multiple notifications are queued, they are shown in order one by one. 
Notification always overrides events and scheduled messages.

Events: messages with some state that are triggered by some action or event in the chat. 
For example if user links a video stream, that might start an event that shows
the streams online-status until it goes offline. Overrides scheduled messages. Events end on predefined
condition or on another action in the chat.

Scheduled messages: content that has been scheduled beforehand with a set timetable, like television scheduling.
For example if weather info is shown each morning on a set time period between 8:00-9:00.
"""


class MessageBoardMessage:
    """
    Message board message with preview that is shown on the pinned
    message section on top of the chat content window.
    """
    # Static id-sequence for all Message Board Messages. Messages are transitive, i.e. they are only stored in memory.
    # Sequence is restarted every time the bot is restarted.
    __id_sequence = itertools.count(start=1)

    def __init__(self,
                 message_board: 'MessageBoard',
                 message: str,
                 preview: str | None = None,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        # Reference to the board on which this message is shown. Used to update content of the message.
        self.message_board: MessageBoard = message_board
        self.id = next(MessageBoardMessage.__id_sequence)
        self.message: str = message
        self.preview: str | None = preview
        self.parse_mode: ParseMode = parse_mode
        # Is the schedule set to end. This is checked each time scheduled message would be updated
        self.schedule_set_to_end: bool = False

    def end_schedule(self) -> None:
        """ Is called when messages schedule ends and new message is set. Signal for the message board message to do
            all and any necessary cleanup. """
        self.schedule_set_to_end = True


class NotificationMessage(MessageBoardMessage):
    """ Notification that is shown on the board for a given duration or default duration. Has precedence over events and
        scheduled messages. """
    _board_notification_update_interval_in_seconds = 5

    def __init__(self,
                 message_board: 'MessageBoard',
                 message: str,
                 preview: str | None = None,
                 duration_in_seconds: int = _board_notification_update_interval_in_seconds,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        super().__init__(message_board, message, preview, parse_mode)
        self.duration_in_seconds = duration_in_seconds


class EventMessage(MessageBoardMessage):
    """ Event message with state and/or conditional ending trigger.  """

    def __init__(self,
                 message_board: 'MessageBoard',
                 message: str,
                 # Given in a situation where event originates from another message in the chat (by user or bot)
                 original_activity_message_id: int | None = None,
                 preview: str | None = None,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        super().__init__(message_board, message, preview, parse_mode)
        # original activity message id can be id of the bots message that this event is based on
        # or id of the message that triggered the event
        self.original_activity_message_id = original_activity_message_id

    def remove_this_message_from_board(self):
        self.message_board.remove_event_by_message_id(self.id)


# Single board for single chat
class MessageBoard:
    # TODO: Should message board have some kind of header like "📋 Ilmoitustaulu 📋"?
    _board_event_update_interval_in_seconds = 30
    """ 
    Base principles of the message board: 
    - One message is pinned on the top of the chat window. That message is the "host message" for the board. 
    - Content of the message can be updated at any time and there is no time limit for bot to edit it's messages.
    - Any content can be added to the message board. The content can be normal static scheduling defined in the code.
    - It can also be a dynamic content that is added by some event in the chat. For example, if a user links a video
      stream that can start an event which updates stats of the video stream to the message board. 
    - Message board can also be used to display short notifications for the users
    """
    # Id-sequence for all update loop tasks. Should be only for logging and debugging purposes.
    __task_id_sequence = itertools.count(start=1)

    def __init__(self, service: 'MessageBoardService', chat_id: int, host_message_id: int):
        # Id of the chat to which the message board belongs
        self.chat_id = chat_id
        # Id of the message that is pinned on the top of the chat window and which is the host message for the board
        self.host_message_id = host_message_id

        # Reference to the message board service instance
        self._service: 'MessageBoardService' = service
        # Current scheduled message on this board
        self._scheduled_message: MessageBoardMessage | None = None
        # Event messages that are rotated in the board
        self._event_messages: List[EventMessage] = []
        # Current event id that is shown in the board. Index cannot be used as events can be added and removed.
        self._current_event_id: int | None = None
        # Task that is periodically called to update the board state
        # None, if there is no current update task. Only needed if there are any event messages.
        self._notification_update_task: asyncio.Task | None = None
        # Same as _notification_update_task but for event messages
        self._event_update_task: asyncio.Task | None = None
        # Notification queue. Notifications are iterated and shown one by one until no notifications are left
        self._notification_queue: List[NotificationMessage] = []

    #
    #   Public methods for updating the message board
    #
    async def set_new_scheduled_message(self, message: MessageBoardMessage) -> None:
        """
        If there is no active event update task, just update the board with the scheduled message.
        Otherwise, the event update loop will take care of updating the board. Sends end schedule event to the previous
        scheduled message (if any and if the message has implemented that).
        :param message: new scheduled message to update to the board
        """
        if self._scheduled_message:
            self._scheduled_message.end_schedule()
        self._scheduled_message = message

        if not self._has_active_event_update_loop():
            await self._set_message_to_board(message)

    async def update_scheduled_message_content(self) -> None:
        """ If there is no active event update task, invoke message board host message content update with current
            scheduled message. Calls Telegram API and edits the message. How to use: update content of the current
            scheduled message and then call this method """
        if not self._has_active_event_update_loop():
            await self._set_message_to_board(self._scheduled_message)

    def add_event_message(self, new_event_message: EventMessage):
        """ Add new event message to the boards event list. Event messages are looped on the board periodically with the
            current scheduled message. """
        self._event_messages.append(new_event_message)

        # If there is no active event loop and there is no active notification loop, start new event update loop task.
        # Otherwise, the event update loop or the notification update loop will take care of updating the board and
        # starting new event loop if needed
        if not self._has_active_event_update_loop() and not self._has_active_notification_loop():
            self._start_new_event_update_loop_as_task()

    def remove_event_by_id(self, event_id: int) -> bool:
        """ Removes event from the message board with given event id.
            :return: True if event was removed. False, if not. """
        event_search_generator = (msg for msg in self._event_messages if msg.id == event_id)
        return self._remove_event_message(event_id, event_search_generator)

    def remove_event_by_message_id(self, message_id: int) -> bool:
        """ Removes event that has given message id as its original activity message id from the boards events.
            :return: True if event was removed. False, if not. """
        event_search_generator = (msg for msg in self._event_messages if msg.original_activity_message_id == message_id)
        return self._remove_event_message(message_id, event_search_generator)

    def add_notification(self, message_notification: NotificationMessage) -> None:
        """ Adds notification to the notification queue. If there is
            :param message_notification: notification to add to the queue. """
        self._notification_queue.append(message_notification)
        if not self._has_active_notification_loop():
            # As a first thing, cancel current event loop if there is one
            if self._has_active_event_update_loop():
                self._event_update_task.cancel()
            self._start_new_notification_update_loop_as_task()

    #
    #   Internal implementation details
    #

    async def _start_notifications_loop(self, loop_id: int):
        """ Loop that updated all notifications in the queue to the board. Notification is updated every n seconds,
            where n is MessageBoard._board_notification_update_interval_in_seconds.
            When notifications have been handled, starts the event update loop or just updates the scheduled message to
            the board. """
        iteration = 0

        while self._notification_queue:
            iteration += 1
            logger.info(f"NOTIFICATION loop Id: {str(loop_id)} iteration: {str(iteration)}")
            # Update the oldest notification in the queue to the queue. Wait for the event update interval and
            # continue to the next iteration of the check loop. Get the oldest notification that hasn't been shown
            # yet and update to the board
            next_notification: NotificationMessage = self._notification_queue.pop(0)
            await self._set_message_to_board(next_notification)
            await asyncio.sleep(next_notification.duration_in_seconds)

        # At the end of the notification loop, check if event loop should be started or just update the scheduled
        # message to the board
        if self._event_messages and not self._has_active_event_update_loop():
            self._start_new_event_update_loop_as_task()
        else:
            await self._set_message_to_board(self._scheduled_message)

    async def _start_event_loop(self, loop_id: int):
        """ Updates board state. First checks if there are notifications in the queue. If so, nothing is done as new
            update is triggered after notifications have been shown.

            If no notifications exist, then event message list is checked. Event messages are rotated in the board with
            the current scheduled event message.

            When there are no notifications or events, the board is updated with the current scheduled message and the
            update loop task completes.
        """
        iteration = 0
        while self._event_messages:
            iteration += 1
            logger.info(f"EVENT loop Id: {str(loop_id)} iteration: {str(iteration)}")
            # Find next event id. If new event id is
            next_event_with_index: Tuple[EventMessage | None, int] = self._find_next_event_with_index()

            # Check if the events have been looped through. If so, update the board with the scheduled message for
            # duration_in_seconds of one event update. If not, update next event
            all_events_rotated = self._current_event_id is not None and next_event_with_index[1] == 0
            if not all_events_rotated:
                await self._update_board_with_next_event_message(next_event_with_index)
                continue

            # Update board with normal scheduled message. If there are no more events or notifications after this
            # iteration, the update loop task is completed and the board is left with current scheduled message.
            await self._set_message_to_board(self._scheduled_message)
            self._current_event_id = None
            await asyncio.sleep(MessageBoard._board_event_update_interval_in_seconds)

        logger.info(f"Event loop Id: {str(loop_id)} - DONE")
        # Set current scheduled message back to the board
        self._current_event_id = None
        await self._set_message_to_board(self._scheduled_message)

    async def _update_board_with_next_event_message(self, next_event_with_index: Tuple[EventMessage | None, int]):
        next_event: EventMessage = next_event_with_index[0]
        self._current_event_id = next_event.id
        await self._set_message_to_board(next_event)
        logger.info(f"Updated board state to event: {next_event.message[:15]}...")
        await asyncio.sleep(MessageBoard._board_event_update_interval_in_seconds)

    def _find_next_event_with_index(self) -> Tuple[EventMessage | None, int]:
        """
        Finds next event message that should be shown in the board. Return None if there are no events.
        :return: Tuple of event message with its index in the event list. Tuple of (None, -1) if there are no events.
        """
        if not self._event_messages:
            return None, -1
        elif self._current_event_id is None or len(self._event_messages) == 1:
            index = 0
            return self._event_messages[index], index

        event_count = len(self._event_messages)
        for (i, event) in enumerate(self._event_messages):
            if event.id == self._current_event_id:
                if i == event_count - 1:
                    index = 0
                    return self._event_messages[index], index
                else:
                    index = i + 1
                    return self._event_messages[index], index
        return None, -1

    async def _set_message_to_board(self, message: MessageBoardMessage):
        if message.preview is not None and message.preview != '':
            content = message.preview + "\n\n" + message.message
        else:
            content = message.message
        try:
            await self._service.application.bot.edit_message_text(
                content, chat_id=self.chat_id, message_id=self.host_message_id, parse_mode=message.parse_mode)
        except telegram.error.BadRequest as e:
            # 'not modified' is expected when trying to update message with same content => ignored.
            if 'not modified' in e.message.lower():
                logger.info("Tried to update message with same content. Ignored.")
                pass
            elif 'not found' in e.message.lower():
                # Message has been deleted.
                self._service.remove_board_from_service_and_chat(self)
            else:
                raise e  # Unexpected error, raise again

    def _has_active_notification_loop(self):
        # Has notification update task, and it is not done or cancelled
        return task_is_active(self._notification_update_task)

    def _has_active_event_update_loop(self):
        # Has event update task, and it is not done or cancelled
        return task_is_active(self._event_update_task)

    def _start_new_notification_update_loop_as_task(self):
        loop_id = next(self.__task_id_sequence)
        task_cancel_log_msg = f"NOTIFICATION loop cancelled. Id: {loop_id}"

        with handle_exception(asyncio.CancelledError, log_msg=task_cancel_log_msg, log_level=logging.INFO):
            logger.info(f"NOTIFICATION loop started. Id: {loop_id}")
            self._notification_update_task = asyncio.create_task(self._start_notifications_loop(loop_id))

    def _start_new_event_update_loop_as_task(self):
        loop_id = next(self.__task_id_sequence)
        task_cancel_log_msg = f"EVENT loop cancelled. Id: {loop_id}"

        with handle_exception(asyncio.CancelledError, log_msg=task_cancel_log_msg, log_level=logging.INFO):
            logger.info(f"EVENT loop started. Id: {loop_id}")
            self._event_update_task = asyncio.create_task(self._start_event_loop(loop_id))

    def _remove_event_message(self, id_value: int | None, generator: Generator[EventMessage, any, None]) -> bool:
        if id_value is None:
            return False
        message: EventMessage | None = next(generator, None)
        if message:
            try:
                self._event_messages.remove(message)
                return True
            except ValueError:
                logging.warning(f"Tried to remove message with id:{message.id}, but it was not found")
                return False  # Message not found, so nothing to remove


def task_is_active(task: asyncio.Task):
    return task is not None and not task.cancelled() and not task.done()

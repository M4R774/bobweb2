import asyncio
import itertools
import logging
from typing import List, Tuple, Generator

import telegram
from telegram import LinkPreviewOptions
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


class MessageWithPreview:
    """ Simple object that contains message with preview and parse mode information. """
    def __init__(self,
                 body: str,
                 preview: str | None = None,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        self.body: str = body
        self.preview: str | None = preview
        self.parse_mode: ParseMode = parse_mode


class MessageBoardMessage(MessageWithPreview):
    """
    Message board message with preview that is shown on the pinned
    message section on top of the chat content window.
    """
    # Static id-sequence for all Message Board Messages. Messages are transitive, i.e. they are only stored in memory.
    # Sequence is restarted every time the bot is restarted.
    __id_sequence = itertools.count(start=1)

    def __init__(self,
                 message_board: 'MessageBoard',
                 body: str,
                 preview: str | None = None,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        # Reference to the board on which this message is shown. Used to update content of the message.
        super().__init__(body, preview, parse_mode)
        self.message_board: MessageBoard = message_board
        self.id = next(MessageBoardMessage.__id_sequence)
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
                 body: str,
                 preview: str | None = None,
                 duration_in_seconds: int | None = None,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        super().__init__(message_board, body, preview, parse_mode)
        self.duration_in_seconds = duration_in_seconds or self._board_notification_update_interval_in_seconds


class EventMessage(MessageBoardMessage):
    """ Event message with state and/or conditional ending trigger.  """

    def __init__(self,
                 message_board: 'MessageBoard',
                 body: str,
                 # Given in a situation where event originates from another message in the chat (by user or bot)
                 original_activity_message_id: int | None = None,
                 preview: str | None = None,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        super().__init__(message_board, body, preview, parse_mode)
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
        # Task that is periodically called to update the board state if there are active events on the board.
        # The update task rotates all events and current scheduled message on the board
        self._event_update_task: asyncio.Task | None = None
        # Notification queue. Notifications are iterated and shown one by one until no notifications are left
        self._notification_queue: List[NotificationMessage] = []
        # Same as _event_update_task but for notification messages
        self._notification_update_task: asyncio.Task | None = None

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

        if not self._has_active_event_update_loop() and not self._has_active_notification_loop():
            await self._set_message_to_board(message)

    async def update_scheduled_message_content(self) -> None:
        """ If there is no active event update task, invoke message board host message content update with current
            scheduled message. Calls Telegram API and edits the message. How to use: update content of the current
            scheduled message and then call this method """
        if not self._has_active_event_update_loop():
            await self._set_message_to_board(self._scheduled_message)

    @handle_exception(asyncio.CancelledError, log_msg="EVENT loop cancelled", log_level=logging.DEBUG)
    def add_event_message(self, new_event_message: EventMessage) -> None:
        """ Add new event message to the boards event list. Event messages are looped on the board periodically with the
            current scheduled message. """
        # If there is no active event loop and there is no active notification loop, start new event update loop task.
        # Otherwise, the event update loop or the notification update loop will take care of updating the board and
        # starting new event loop if needed
        self._event_messages.append(new_event_message)
        if not self._has_active_event_update_loop() and not self._has_active_notification_loop():
            logger.debug(f"EVENT loop started")
            self._event_update_task = asyncio.create_task(self._start_event_loop())

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

    @handle_exception(asyncio.CancelledError, log_msg="NOTIFICATION loop cancelled.", log_level=logging.DEBUG)
    def add_notification(self, message_notification: NotificationMessage) -> None:
        """ Adds notification to the notification queue. If there is
            :param message_notification: notification to add to the queue. """
        self._notification_queue.append(message_notification)
        if not self._has_active_notification_loop():
            logger.debug(f"NOTIFICATION loop started")
            self._notification_update_task = asyncio.create_task(self._start_notifications_loop())

    #
    #   Internal implementation details
    #

    async def _start_notifications_loop(self):
        """ Loop that updated all notifications in the queue to the board. Notification is updated every n seconds,
            where n is MessageBoard._board_notification_update_interval_in_seconds.
            When notifications have been handled, starts the event update loop or just updates the scheduled message to
            the board. """
        iteration = 0
        notification_loop_done = False
        while not notification_loop_done:
            iteration += 1
            logger.debug(f"NOTIFICATION loop - iteration: {str(iteration)}")
            notification_loop_done, delay = await self._do_notifications_loop_iteration()
            if delay:
                await asyncio.sleep(delay)
        logger.debug(f"NOTIFICATION loop - DONE")

    async def _do_notifications_loop_iteration(self) -> (bool, int):
        """ Does one iteration of the notification loop logic.
            :return: True, if the loop is done and there are no notifications. False, if loop is not done. """
        if self._notification_queue:
            # Update the oldest notification in the queue to the queue. Wait for the event update interval and
            # continue to the next iteration of the check loop. Get the oldest notification that hasn't been shown
            # yet and update to the board
            next_notification: NotificationMessage = self._notification_queue.pop(0)
            await self._set_message_to_board(next_notification)
            return False, next_notification.duration_in_seconds

        # As there might be an event loop running in the background (that does not update events to the board as long
        # as there are notifications), check if there is a current event in the rotation OR scheduled message that
        # should be updated to the board. This is done so that a short notification does not reset current event
        # rotation
        next_message = self._find_current_event() or self._scheduled_message
        await self._set_message_to_board(next_message)
        return True, None

    async def _start_event_loop(self):
        """ Updates board state. First checks if there are notifications in the queue. If so, nothing is done as new
            update is triggered after notifications have been shown.

            If no notifications exist, then event message list is checked. Event messages are rotated in the board with
            the current scheduled event message.

            When there are no notifications or events, the board is updated with the current scheduled message and the
            update loop task completes.
        """
        iteration = 0
        event_loop_done = False
        while not event_loop_done:
            iteration += 1
            logger.debug(f"EVENT loop - iteration: {str(iteration)}")
            event_loop_done = await self._do_event_loop_iteration()
            if not event_loop_done:
                await asyncio.sleep(MessageBoard._board_event_update_interval_in_seconds)

        logger.debug(f"EVENT loop - DONE")

    async def _do_event_loop_iteration(self) -> bool:
        if self._event_messages:
            # Find next event id. If new event id is
            next_event: EventMessage | None = self._find_next_event()

            # If next message is event, it's id is set as current event. Otherwise, its scheduled messages turn in
            # rotation -> no current event -> set as None
            self._current_event_id = next_event.id if next_event else None
            next_message: MessageBoardMessage = next_event or self._scheduled_message

            # Update next event or scheduled message to the board and wait
            await self._set_message_to_board_if_no_notifications(next_message)
            return False

        # If scheduled message is not currently displayed on the board, set it back to the board
        if self._current_event_id:
            self._current_event_id = None
            await self._set_message_to_board_if_no_notifications(self._scheduled_message)
        return True

    def _find_current_event(self) -> EventMessage | None:
        """ :return: Current event in the event rotation or none if no event loop
                     OR scheduled messages turn in the rotation """
        for event in self._event_messages:
            if event.id == self._current_event_id:
                return event
        return None

    def _find_next_event(self) -> EventMessage | None:
        """ :return: Finds next event message that should be shown in the board. Return None if there are no events
                     OR scheduled message should be shown next """
        if not self._event_messages:
            return None
        elif self._current_event_id is None:
            return self._event_messages[0]

        last_event_index = len(self._event_messages) - 1
        for (i, event) in enumerate(self._event_messages):
            if event.id == self._current_event_id:
                if i < last_event_index:
                    return self._event_messages[i + 1]
        # All events rotated, return None
        return None

    async def _set_message_to_board(self, message: MessageBoardMessage):
        if message.preview is not None and message.preview != '':
            content = message.preview + "\n\n" + message.body
        else:
            content = message.body
        try:
            link_preview_options: LinkPreviewOptions = LinkPreviewOptions(prefer_small_media=True)
            await self._service.application.bot.edit_message_text(text=content,
                                                                  chat_id=self.chat_id,
                                                                  message_id=self.host_message_id,
                                                                  parse_mode=message.parse_mode,
                                                                  link_preview_options=link_preview_options)
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

    async def _set_message_to_board_if_no_notifications(self, message: MessageBoardMessage):
        """ Same as _set_message_to_board, but message is only updated if there is no notification loop going on """
        if not self._notification_queue and not self._has_active_notification_loop():
            await self._set_message_to_board(message)

    def _has_active_notification_loop(self):
        # Has notification update task, and it is not done or cancelled
        return task_is_active(self._notification_update_task)

    def _has_active_event_update_loop(self):
        # Has event update task, and it is not done or cancelled
        return task_is_active(self._event_update_task)

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

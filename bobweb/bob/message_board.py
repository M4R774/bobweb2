import asyncio
import itertools
import logging
from typing import List, Callable, Awaitable, Dict

from telegram.constants import ParseMode

from bobweb.bob.activities.command_activity import CommandActivity

logger = logging.getLogger(__name__)

"""
Message board can have three types of message:s notifications, events and scheduled messages.

Notifications: short messages that are shown for a given short duration.
If multiple notifications are queued, they are shown in order one by one. 
Notification always overrides events and scheduled messages.

Events: messages with some state that are triggered by some action or event in the chat. 
For example if user links a video stream, that might start an event that shows
the streams online-status until it goes offline. Overrides scheduled messages. Events end on predefined
condition or on another action in the chat.

Scheduled messages: content that has been scheduled beforehand with a set timetable, like television scheduling.
For example if weather info is shown each morning on a set time period between 8:00-9:00.
"""


# class MessageIdentifier:
#     """ Simple class for explicit message identifier that consists of both chat and message ids """
#     def __init__(self, chat_id: int, message_id: int):
#         self.chat_id = chat_id
#         self.message_id = message_id

class MessageBoardMessage:
    """
    Message board message with preview that is shown on the pinned
    message section on top of the chat content window.
    """
    # Static id-sequence for all Message Board Messages. Messages are transitive, i.e. they are only stored in memory.
    # Sequence is restarted every time the bot is restarted.
    __id_sequence = itertools.count(start=1)

    def __init__(self,
                 message: str,
                 preview: str | None,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        self.id = next(MessageBoardMessage.__id_sequence)
        self.message: str = message
        self.preview: str = preview
        self.parse_mode: ParseMode = parse_mode
        # Reference to the board on which this message is shown. Used to update content of the message.
        self.message_board: MessageBoard | None = None

    async def post_construct_hook(self) -> None:
        """ Asynchronous post construct hook that is called after the message is created. """
        pass

    async def update_content_to_board(self):
        """ Updates current content to the board. """
        await self.message_board.set_message_to_board(self)


class NotificationMessage(MessageBoardMessage):
    """ Short notification that is shown for a given duration """

    def __init__(self,
                 message: str,
                 preview: str | None,
                 duration: int,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        super().__init__(message, preview, parse_mode)
        self.duration = duration


class EventMessage(MessageBoardMessage):
    """ Event message with state and/or conditional ending trigger.  """

    def __init__(self,
                 message: str,
                 preview: str | None,
                 original_activity_message_id: int,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        super().__init__(message, preview, parse_mode)
        self.original_activity_message_id = original_activity_message_id

    async def remove_this_message_from_board(self):
        await self.message_board.remove_event_message(self.id)


class DynamicMessageBoardMessage(MessageBoardMessage):
    """
    Same as scheduled message but with inner state control and dynamic content. Can update it's content during the
    schedule. When schedule ends, end_schedule is called.
    """

    def __init__(self,
                 board: 'MessageBoard',
                 message: str = None,
                 preview: str = None):
        self.board = board
        super().__init__(message, preview)

    # async def set_preview(self, new_preview: str):
    #     self.preview = new_preview
    #     await self.update_preview_func(new_preview)
    #
    # async def set_message(self, new_message: str):
    #     self.message = new_message
    #     await self.update_message_func(new_message)

    def end_schedule(self):
        """
        Is called when messages schedule ends and new message is set.
        :return:
        """
        pass


# class MessageBoardProvider:
#
#     async def create_message_with_preview(self, chat_id: int) -> MessageBoardMessage:
#         raise NotImplementedError("Not implemented by inherited class")


# Single board for single chat
class MessageBoard:
    # TODO: Should message board have some kind of header like "📋 Ilmoitustaulu 📋"?
    board_event_update_interval_in_seconds = 30
    board_notification_update_interval_in_seconds = 5
    """ 
    Base principles of the message board: 
    - One message is pinned on the top of the chat window. That message is the "host message" for the board. 
    - Content of the message can be updated at any time and there is no time limit for bot to edit it's messages.
    - Any content can be added to the message board. The content can be normal static scheduling defined in the code.
    - It can also be a dynamic content that is added by some event in the chat. For example, if a user links a video
      stream that can start an event which updates stats of the video stream to the message board. 
    - Message board can also be used to display short notifications for the users
    """

    def __init__(self, service: 'MessageBoardService', chat_id: int, host_message_id: int):
        self.service: 'MessageBoardService' = service
        self.chat_id = chat_id
        self.host_message_id = host_message_id
        # Current scheduled message on this board
        self.scheduled_message: MessageBoardMessage | None = None
        # Event messages that are rotated in the board
        self.event_messages: List[EventMessage] = []
        # Current event id that is shown in the board
        self.current_event_id: int | None = None
        # Task that is periodically called to update the board state
        # None, if there is no current update task. Only needed if there are any event messages.
        self.event_update_task: asyncio.Task | None = None
        # Notification queue. Notifications are iterated and shown one by one until no notifications are left
        self.notification_queue: List[NotificationMessage] = []

    async def update_board_state_loop(self):
        """ Updates board state. First checks if there are notifications in the queue. If so, nothing is done as new
            update is triggered after notifications have been shown.

            If no notifications exist, then event message list
            is checked. If multiple events exists, cycles to the next event in the list. If only one event exists, it is
            shown.

            If no notifications and no events exist, then scheduled message is shown. """
        # First loop through notifications and display each one in order
        while self.notification_queue:
            # Get the oldest notification that hasn't been shown yet and update to the board
            next_notification = self.notification_queue.pop(0)
            await self.set_message_to_board(next_notification)
            await asyncio.sleep(MessageBoard.board_event_update_interval_in_seconds)

        # Second loop that is looped for as long as there are any events
        while self.event_messages:
            # Find next event id. As the events are rotated, id for the current event is stored
            next_event = self.__find_next_event()
            self.current_event_id = next_event.id
            await self.set_message_to_board(next_event)
            await asyncio.sleep(MessageBoard.board_event_update_interval_in_seconds)

        # Return to normal scheduling
        self.current_event_id = None
        await self.set_message_to_board(self.scheduled_message)

    async def update_board_state_after_delay(self):
        """ For creating tasks to schedule board state updates.
            As events are added and removed, index cannot be used. Find next event in the list after current event """
        try:
            await asyncio.sleep(MessageBoard.board_event_update_interval_in_seconds)
            await self.update_board_state_loop()
        except asyncio.CancelledError:
            pass  # If task is cancelled, do nothing

    def __find_next_event(self) -> EventMessage | None:
        if not self.event_messages:
            return None
        elif self.current_event_id is None:
            return self.event_messages[0]

        event_count = len(self.event_messages)
        for (i, event) in enumerate(self.event_messages):
            if event.id == self.current_event_id:
                if i == event_count - 1:
                    return self.event_messages[0]
                else:
                    return self.event_messages[i + 1]
        return None

    async def set_message_to_board(self, message: MessageBoardMessage):
        message.message_board = self
        if message.preview is not None and message.preview != '':
            content = message.preview + "\n\n" + message.message
        else:
            content = message.message
        await self.service.application.bot.edit_message_text(
            content, chat_id=self.chat_id, message_id=self.host_message_id, parse_mode=message.parse_mode)

    async def set_scheduled_message(self, message: MessageBoardMessage):
        self.scheduled_message = message
        await self.set_message_to_board(message)

    async def add_event_message(self, new_event_message: EventMessage):
        """ Add new event message to the boards event list """
        self.event_messages.append(new_event_message)
        # self.current_event_id = new_event_message.id
        # await self.set_message_to_board(new_event_message)

        # If there are multiple events, start scheduled board update task
        if self.should_start_update_loop:
            self.start_new_update_loop()

    def should_start_update_loop(self):
        has_no_active_update_loop = self.event_update_task is None or self.event_update_task.done()
        has_notifications_or_events = self.notification_queue or self.event_messages
        return has_no_active_update_loop and has_notifications_or_events

    def start_new_update_loop(self):
        self.event_update_task = asyncio.get_running_loop().create_task(self.update_board_state_loop())

    async def remove_event_message(self, event_id: int):
        message = next((msg for msg in self.event_messages if msg.id == event_id), None)
        if message:
            try:
                self.event_messages.remove(message)
            except ValueError:
                logging.warning(f"Tried to remove message with id:{event_id}, but it was not found")
                pass  # Message not found, so nothing to remove

            await self.update_board_state_loop()

    def add_notification(self, message_notification: NotificationMessage):
        self.notification_queue.append(message_notification)

    # def get_default_msg_set_call_back(self) -> callable:
    #     return self.set_default_msg
    #
    # def get_notification_add_call_back(self) -> callable:
    #     return self.add_notification

# Command Service that creates and stores all reference to all 'message_board' messages
# and manages messages
# is initialized below on first module import. To get instance, import it from below

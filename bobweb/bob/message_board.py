from typing import List, Callable, Awaitable, Dict

from telegram.constants import ParseMode

from bobweb.bob.activities.command_activity import CommandActivity

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
    def __init__(self,
                 message: str,
                 preview: str | None,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        self.message: str = message
        self.preview: str = preview
        self.parse_mode: ParseMode = parse_mode
        self.message_board: MessageBoard = None

    async def post_construct_hook(self) -> None:
        """ Asynchronous post construct hook that is called after the message is created. """
        pass


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

    def __init__(self, service: 'MessageBoardService', chat_id: int, host_message_id: int):
        self.service: 'MessageBoardService' = service
        self.chat_id = chat_id
        self.host_message_id = host_message_id
        # Current scheduled message on this board
        self.scheduled_message: MessageBoardMessage = None
        # Event messages that are rotated in the board
        self.event_messages: List[EventMessage] = []
        # Notification queue. Notifications are iterated and shown one by one until no notifications are left
        self.notification_queue: List[NotificationMessage] = []

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
        self.event_messages.append(new_event_message)
        # If this is the only event, update message immediately
        if len(self.event_messages) == 1:
            await self.set_message_to_board(new_event_message)

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

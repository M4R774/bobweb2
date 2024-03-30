from typing import List, Callable, Awaitable

from telegram.constants import ParseMode

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


class NotificationMessage:
    """ Short notification that is shown for a given duration """
    def __init__(self, content: str, duration: int):
        self.content = content
        self.duration = duration


class EventMessage:
    """ Event message with state and/or conditional ending trigger """
    def __init__(self, content: str, duration: int):
        self.content = content
        self.duration = duration


class ScheduledMessage:
    """
    Longer message board message with preview that is shown on the pinned
    message section on top of the chat content window.
    """
    def __init__(self,
                 message: str,
                 preview: str,
                 parse_mode: ParseMode = ParseMode.MARKDOWN):
        self.message: str = message
        self.preview: str = preview
        self.parse_mode: ParseMode = parse_mode
        self.message_board: MessageBoard = None

    async def post_construct_hook(self) -> None:
        """ Asyncronous post construct hook that is called after the message is created. """
        pass


class DynamicScheduledMessage(ScheduledMessage):
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
#     async def create_message_with_preview(self, chat_id: int) -> ScheduledMessage:
#         raise NotImplementedError("Not implemented by inherited class")


# Single board for single chat
class MessageBoard:
    def __init__(self, service: 'MessageBoardService', chat_id: int, host_message_id: int):
        self.service: 'MessageBoardService' = service
        self.chat_id = chat_id
        self.host_message_id = host_message_id

        self.scheduled_message: ScheduledMessage = None
        self.notification_queue: List[NotificationMessage] = []

    # async def set_default_msg(self, content: str):
    #     self.default_msg = content
    #     await self.service.application.bot.edit_message_text(content, chat_id=self.chat_id, message_id=self.host_message_id)

    async def set_message_with_preview(self, message: ScheduledMessage):
        self.scheduled_message = message
        content = message.preview + "\n\n📋 Ilmoitustaulu 📋\n" + message.message
        await self.service.application.bot.edit_message_text(
            content, chat_id=self.chat_id, message_id=self.host_message_id, parse_mode=message.parse_mode)

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

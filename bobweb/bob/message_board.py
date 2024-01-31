from typing import List

from telegram.constants import ParseMode

"""
Message board can have three types of messages notifications, events and scheduled messages.

Notifications: short messages that are shown for a given duration.
If multiple notifications are queued, they are shown in order one by one. 
Notification always overrides events and scheduled messages.

Events: messages with some state that are triggered by some action in the chat. 
For example if user links a video stream, that might start an event that shows
the streams online-status until it goes offline. Overrides scheduled messages. Events end on predefined
condition or on another action in the chat.

Scheduled messages: content that has been scheduled beforehand with a set timetable.
For example if weather info is shown each morning on a set time period.
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
    def __init__(self, message: str, preview: str):
        self.message = message
        self.preview = preview


class MessageBoardProvider:

    async def create_message_with_preview(self, chat_id: int) -> ScheduledMessage:
        raise NotImplementedError("Not implemented by inherited class")


# Single board for single chat
class MessageBoard:
    def __init__(self, service: 'MessageBoardService', chat_id: int, host_message_id: int):
        self.service: 'MessageBoardService' = service
        self.chat_id = chat_id
        self.host_message_id = host_message_id

        self.default_msg: str = 'HYVÄÄ HUOMENTA!'
        self.notification_queue: List[NotificationMessage] = []

    async def set_default_msg(self, content: str):
        self.default_msg = content
        await self.service.application.bot.edit_message_text(content, chat_id=self.chat_id, message_id=self.host_message_id)

    async def set_message_with_preview(self, message: ScheduledMessage, parse_mode: ParseMode = None):
        content = message.preview + "\n\n[Ilmoitustaulu]\n" + message.message
        await self.service.application.bot.edit_message_text(
            content, chat_id=self.chat_id, message_id=self.host_message_id, parse_mode=parse_mode)

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

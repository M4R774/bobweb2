import datetime
import os
from typing import List

import django
from telegram import Bot
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.utils_common import has
from bobweb.web.bobapp.models import Chat


class MessageNotification:
    def __init__(self, content: str, duration: int):
        self.content = content
        self.duration = duration


# Single board for single chat
class MessageBoard:
    def __init__(self, bot: Bot, chat_id: int, host_message_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.host_message_id = host_message_id

        self.default_msg: str = 'HYVÄÄ HUOMENTA!'
        self.notification_queue: List[MessageNotification] = []

    def set_default_msg(self, content: str):
        self.default_msg = content
        self.bot.edit_message_text(content, chat_id=self.chat_id, message_id=self.host_message_id)

    def add_notification(self, message_notification: MessageNotification):
        self.notification_queue.append(message_notification)

    def get_default_msg_set_call_back(self) -> callable:
        return self.set_default_msg

    def get_notification_add_call_back(self) -> callable:
        return self.add_notification



# Command Service that creates and stores all reference to all 'message_board' messages
# and manages messages
# is initialized below on first module import. To get instance, import it from below
class MessageBoardService:


    def __init__(self, bot: Bot):
        self.bot = bot
        self.boards: List[MessageBoard] = []

        chats: List[Chat] = list(database.get_chats())
        for chat in chats:
            if has(chat.message_board_msg_id):
                board = MessageBoard(bot=self.bot, chat_id=chat.id, host_message_id=chat.message_board_msg_id)
                self.boards.append(board)

    def get_board(self, chat_id) -> MessageBoard | None:
        for board in self.boards:
            if board.chat_id == chat_id:
                return board
        return None

#
# singleton instance of command service
#
instance: MessageBoardService | None = None
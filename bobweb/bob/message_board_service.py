import datetime
import os
from typing import List, Callable, Any, Awaitable

import django
from telegram import Bot
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, Application

from bobweb.bob import database, command_sahko
from bobweb.bob.message_board import MessageBoard, ScheduledMessage
from bobweb.bob.utils_common import has
from bobweb.web.bobapp.models import Chat


# Command Service that creates and stores all reference to all 'message_board' messages
# and manages messages
# is initialized below on first module import. To get instance, import it from below
class MessageBoardService:
    """
    Service for handling message boards. Initiates board for each chat that has message board set
    previously on startup. Adds new boards or re-pins existing boards on message board command.
    """

    def __init__(self, application: Application):
        self.application: Application = application
        self.boards: List[MessageBoard] = []

        # Initialize message board for each chat that has message board set
        for chat in database.get_chats_with_message_board():
            if has(chat.message_board_msg_id):
                board = MessageBoard(service=self, chat_id=chat.id, host_message_id=chat.message_board_msg_id)
                self.boards.append(board)

        async def set_electricity_price(context: CallbackContext):
            await self.update_all_boards_with_provider(command_sahko.create_message_with_preview,
                                                       parse_mode=ParseMode.HTML)

        application.job_queue.run_once(set_electricity_price, 0)

    async def update_all_boards(self, message: ScheduledMessage):
        for board in self.boards:
            await board.set_message_with_preview(message)

    async def update_all_boards_with_provider(self,
                                              message_provider: Callable[[int], Awaitable[ScheduledMessage]],
                                              parse_mode: ParseMode = ParseMode.MARKDOWN):
        """
        Updates all boards by calling message_provider for each board with its chats id as parameter
        :param message_provider: Callable that produces awaitable coroutine with ScheduledMessage
        :param parse_mode: parse mode for the messages
        """
        for board in self.boards:
            message = await message_provider(board.chat_id)
            await board.set_message_with_preview(message, parse_mode)

    def find_board(self, chat_id) -> MessageBoard | None:
        for board in self.boards:
            if board.chat_id == chat_id:
                return board
        return None

    def create_new_board(self, chat_id, message_id) -> MessageBoard:
        new_board = MessageBoard(service=self, chat_id=chat_id, host_message_id=message_id)
        self.boards.append(new_board)
        return new_board


#
# singleton instance of this service
#
instance: MessageBoardService | None = None

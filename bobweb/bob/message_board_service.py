import datetime
from typing import List, Callable, Awaitable, Tuple

from telegram.ext import Application, CallbackContext

from bobweb.bob import database, command_sahko
from bobweb.bob.command_weather import create_weather_scheduled_message
from bobweb.bob.message_board import MessageBoard, ScheduledMessage
from bobweb.bob.utils_common import has


class ScheduledMessageTiming:
    def __init__(self,
                 starting_from: datetime.time,
                 message_provider: Callable[[int], Awaitable[ScheduledMessage]]):
        self.starting_from = starting_from
        self.message_provider = message_provider


async def dummy(chat_id) -> ScheduledMessage:
    return ScheduledMessage('dummy', 'dummy')

# Default schedule for the day. Times are in UTC+-0
default_daily_schedule = [
    ScheduledMessageTiming(datetime.time(4, 30), create_weather_scheduled_message),  # Weather
    ScheduledMessageTiming(datetime.time(7, 00), command_sahko.create_message_with_preview),  # Electricity
    # ScheduledMessageTiming(datetime.time(10, 00), dummy),  # Daily quote
    ScheduledMessageTiming(datetime.time(13, 00), dummy),  # Random receipt
    ScheduledMessageTiming(datetime.time(16, 00), dummy),  # Epic Games game
    ScheduledMessageTiming(datetime.time(19, 00), dummy),  # Good night
]

# default_daily_schedule = [
#     ScheduledMessageTiming(datetime.time(4, 30), create_weather_scheduled_message),  # Weather
# ]

update_cron_job_name = 'update_boards_and_schedule_next_change'


def find_current_and_next_scheduling() -> Tuple[ScheduledMessageTiming, ScheduledMessageTiming]:
    # Find current scheduledMessageTiming that should be currently active. Initiated with last timing of the day.
    current_scheduled_index = len(default_daily_schedule) - 1
    current_schedule = default_daily_schedule[current_scheduled_index]  # Init with the last item
    current_time = datetime.datetime.now().time()

    for (i, scheduling) in enumerate(default_daily_schedule):
        # Find last scheduled message which starting time is before current time
        if current_time > scheduling.starting_from:
            current_scheduled_index = i
            current_schedule = scheduling

    if current_scheduled_index == len(default_daily_schedule) - 1:
        return current_schedule, default_daily_schedule[0]
    else:
        return current_schedule, default_daily_schedule[current_scheduled_index + 1]


# Command Service that creates and stores all reference to all 'message_board' messages
# and manages messages
# is initialized below on first module import.
class MessageBoardService:
    """
    Service for handling message boards. Initiates board for each chat that has message board set
    previously on startup. Adds new boards or re-pins existing boards on message board command.
    """

    def __init__(self, application: Application):
        self.application: Application = application
        self.boards: List[MessageBoard] = self.init_all_message_boards_for_chats()

        # async def set_electricity_price(context: CallbackContext):
        #     await self.update_all_boards_with_provider(command_sahko.create_message_with_preview,
        #                                                parse_mode=ParseMode.HTML)
        #
        # application.job_queue.run_once(set_electricity_price, 0)

    def init_all_message_boards_for_chats(self) -> List[MessageBoard]:
        # Initialize message board for each chat that has message board set
        boards = []
        for chat in database.get_chats_with_message_board():
            if has(chat.message_board_msg_id):
                board = MessageBoard(service=self, chat_id=chat.id, host_message_id=chat.message_board_msg_id)
                boards.append(board)
        return boards

    async def update_boards_and_schedule_next_update(self, context: CallbackContext = None):
        # Find current and next scheduling. Update current scheduling message to all boards and schedule next change
        # at the start of the next scheduling.
        if not self.boards:
            return  # No message boards

        current_scheduling, next_scheduling = find_current_and_next_scheduling()
        for board in self.boards:
            await update_message_board_with_current_scheduling(board, current_scheduling)

        self.schedule_next_update(next_scheduling)

    def schedule_next_update(self, next_scheduling: ScheduledMessageTiming):
        # Schedule next change only if there is no update task currently scheduled
        current_update_jobs = self.application.job_queue.get_jobs_by_name(update_cron_job_name)
        if not current_update_jobs:
            # Calculate next scheduling start time and add it to the job queue to be run once
            next_scheduling_start_dt = datetime.datetime.combine(datetime.date.today(), next_scheduling.starting_from)
            self.application.job_queue.run_once(callback=self.update_boards_and_schedule_next_update,
                                                when=next_scheduling_start_dt,
                                                name=update_cron_job_name)

    # async def update_all_boards(self, message: ScheduledMessage):
    #     for board in self.boards:
    #         await board.set_message_with_preview(message)

    # async def update_all_boards_with_provider(self,
    #                                           message_provider: Callable[[int], Awaitable[ScheduledMessage]],
    #                                           parse_mode: ParseMode = ParseMode.MARKDOWN):
    #     """
    #     Updates all boards by calling message_provider for each board with its chats id as parameter
    #     :param message_provider: Callable that takes chat id as parameter and produces awaitable
    #                              coroutine with ScheduledMessage
    #     :param parse_mode: parse mode for the messages
    #     """
    #     for board in self.boards:
    #         message = await message_provider(board.chat_id)
    #         await board.set_message_with_preview(message, parse_mode)

    def find_board(self, chat_id) -> MessageBoard | None:
        for board in self.boards:
            if board.chat_id == chat_id:
                return board
        return None

    async def create_new_board(self, chat_id, message_id) -> MessageBoard:
        new_board = MessageBoard(service=self, chat_id=chat_id, host_message_id=message_id)
        self.boards.append(new_board)

        # Start board with scheduled message
        current_scheduling, next_scheduling = find_current_and_next_scheduling()
        await update_message_board_with_current_scheduling(new_board, current_scheduling)
        self.schedule_next_update(next_scheduling)
        return new_board


async def update_message_board_with_current_scheduling(board: MessageBoard,
                                                       current_scheduling: ScheduledMessageTiming):
    # constructor call that creates new scheduled message
    message: ScheduledMessage = await current_scheduling.message_provider(board.chat_id)
    message.message_board = board  # Set board reference
    await message.post_construct_hook()
    await board.set_message_with_preview(message)


#
# singleton instance of this service
#
instance: MessageBoardService | None = None

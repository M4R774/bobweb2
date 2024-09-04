import datetime
from typing import List, Callable, Awaitable, Tuple

import telegram
from telegram.ext import Application, CallbackContext

from bobweb.bob import main, database, command_sahko, command_ruoka, command_epic_games
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.command_weather import create_weather_scheduled_message
from bobweb.bob.message_board import MessageBoard, MessageBoardMessage
from bobweb.bob.utils_common import has


class ScheduledMessageTiming:
    def __init__(self,
                 starting_from: datetime.time,
                 message_provider: Callable[[int], Awaitable[MessageBoardMessage]]
                                   | Callable[[], Awaitable[MessageBoardMessage]],
                 is_chat_specific: bool = True):
        self.starting_from = starting_from
        self.message_provider = message_provider
        # If scheduled message is chat specific, each message is created separately for each board and the chat id is
        # given as a parameter to the message_provider. Otherwise the scheduled message is created only once and the
        # same result is updated to each chats message board.
        self.is_chat_specific = is_chat_specific  #TODO: Jos chat-kohtainen, tehdään chateittäin. Muuten ilman


async def dummy() -> MessageBoardMessage:
    return MessageBoardMessage('dummy', 'dummy')


def create_timing(hour: int, minute: int, message_provider: Callable[[], Awaitable[MessageBoardMessage]]):
    return ScheduledMessageTiming(datetime.time(hour, minute), message_provider, is_chat_specific=False)


def create_chat_specific_timing(hour: int, minute: int, message_provider: Callable[[int], Awaitable[MessageBoardMessage]]):
    return ScheduledMessageTiming(datetime.time(hour, minute), message_provider, is_chat_specific=True)


# Default schedule for the day. Times are in UTC+-0
default_daily_schedule = [
    create_chat_specific_timing(4, 30, create_weather_scheduled_message),           # Weather
    create_chat_specific_timing(7, 00, command_sahko.create_message_with_preview),  # Electricity
    # ScheduledMessageTiming(datetime.time(10, 00), dummy),  # Daily quote
    create_timing(13, 00, command_ruoka.create_message_board_daily_message),    # Random receipt
    create_timing(19, 00, dummy),  # Good night
]

thursday_schedule = [
    create_chat_specific_timing(4, 30, create_weather_scheduled_message),       # Weather
    create_chat_specific_timing(7, 00, command_sahko.create_message_with_preview),            # Electricity
    # ScheduledMessageTiming(datetime.time(10, 00), dummy),  # Daily quote
    create_timing(13, 00, command_ruoka.create_message_board_daily_message),    # Random receipt
    create_timing(19, 00, dummy),  # Good night
    # Epic Games free games offering is only shown on thursday
    ScheduledMessageTiming(datetime.time(16, 00), command_epic_games.create_message_board_daily_message),
]


def get_schedule_for_weekday(weekday_index: int = 0) -> List[ScheduledMessageTiming]:
    # weekday = 0 is Monday
    if weekday_index == 1:
        return thursday_schedule
    else:
        return default_daily_schedule


update_cron_job_name = 'update_boards_and_schedule_next_change'


def find_current_and_next_scheduling() -> Tuple[ScheduledMessageTiming, ScheduledMessageTiming]:
    # Find current scheduledMessageTiming that should be currently active. Initiated with last timing of the day.
    weekday_today = datetime.datetime.now().weekday()
    schedule_today = get_schedule_for_weekday(weekday_today)

    current_scheduled_index = None
    current_time = datetime.datetime.now().time()

    for (i, scheduling) in enumerate(schedule_today):
        # Find last scheduled message which starting time is before current time
        if current_time > scheduling.starting_from:
            current_scheduled_index = i
            current_schedule = scheduling

    if current_scheduled_index is None:
        # First of day
        return schedule_today[0], schedule_today[1]
    elif current_scheduled_index == len(schedule_today) - 1:
        # Last of day. Return current and the first of the next day.
        weekday_tomorrow = 0 if weekday_today == 6 else weekday_today + 1
        return schedule_today[current_scheduled_index], get_schedule_for_weekday(weekday_tomorrow)[0]
    else:
        return schedule_today[current_scheduled_index], schedule_today[current_scheduled_index + 1]


# Command Service that creates and stores all reference to all 'message_board' messages
# and manages messages. Is initialized below on first module import.
class MessageBoardService:
    """
    Service for handling message boards. Initiates board for each chat that has message board set
    previously on startup. Adds new boards or re-pins existing boards on message board command.
    """

    def __init__(self, application: Application):
        self.application: Application = application
        self.boards: List[MessageBoard] = self.init_all_message_boards_for_chats()

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

        if current_scheduling.is_chat_specific:
            # Create chat specific message for each board and update it to the board
            for board in self.boards:
                await update_message_board_with_current_scheduling(board, current_scheduling)
        else:
            # Create message board message once and update it to each board
            message = await current_scheduling.message_provider()
            for board in self.boards:
                await board.set_scheduled_message(message)

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
    # Initializer call that creates new scheduled message
    message: MessageBoardMessage = await current_scheduling.message_provider(board.chat_id)
    await board.set_scheduled_message(message)

#
# singleton instance of this service
#
instance: MessageBoardService | None = None

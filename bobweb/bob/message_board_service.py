import datetime
from typing import List, Callable, Awaitable, Tuple

from telegram.ext import Application, CallbackContext

from bobweb.bob import main, database, command_sahko, command_ruoka, command_epic_games, good_night_wishes
from bobweb.bob.command_weather import create_weather_scheduled_message
from bobweb.bob.message_board import MessageBoard, MessageBoardMessage, MessageWithPreview, NotificationMessage
from bobweb.bob.utils_common import has


class ScheduledMessageTiming:
    """
    Represents a scheduled message timing. Contains starting time without date, message provider which returns the
    scheduled message and whether the message is chat specific or not. If message is chat specific, new
    MessageBoardMessage should be created by the message provider. If the schedule is not chat specific, message
    provider returns content of the message from which is then created messages for all the boards.
    """

    def __init__(self,
                 starting_from: datetime.time,
                 # Is either function that takes board and chat_id to produce messageBoardMessage
                 # OR is provider, that provides contents of the message from which new message is created for each chat
                 message_provider: Callable[[MessageBoard, int], Awaitable[MessageBoardMessage]]
                                   | Callable[[], Awaitable[MessageWithPreview]],
                 is_chat_specific: bool = False):
        self.starting_from = starting_from
        self.message_provider = message_provider
        # If scheduled message is chat specific, each message is created separately for each board and the chat id is
        # given as a parameter to the message_provider. Otherwise, the scheduled message is created only once and the
        # same result is updated to each chats message board.
        self.is_chat_specific = is_chat_specific


def create_schedule(hour: int, minute: int, message_provider: Callable[[], Awaitable[MessageWithPreview]]):
    return ScheduledMessageTiming(datetime.time(hour, minute), message_provider)


def create_schedule_with_chat_context(hour: int, minute: int,
                                      message_provider: Callable[[MessageBoard, int], Awaitable[MessageBoardMessage]]):
    return ScheduledMessageTiming(datetime.time(hour, minute), message_provider, is_chat_specific=True)


# Default schedule for the day. Times are in UTC+-0
default_daily_schedule = [
    create_schedule_with_chat_context(4, 00, create_weather_scheduled_message),  # Weather
    create_schedule_with_chat_context(7, 00, command_sahko.create_message_with_preview),  # Electricity
    create_schedule(13, 00, command_ruoka.create_message_board_daily_message),  # Random receipt
    create_schedule(19, 00, good_night_wishes.create_good_night_message),  # Good night
]

thursday_schedule = [
    create_schedule_with_chat_context(4, 00, create_weather_scheduled_message),  # Weather
    create_schedule_with_chat_context(7, 00, command_sahko.create_message_with_preview),  # Electricity
    create_schedule(13, 00, command_ruoka.create_message_board_daily_message),  # Random receipt
    create_schedule(16, 00, command_epic_games.create_message_board_daily_message),
    create_schedule(19, 00, good_night_wishes.create_good_night_message),  # Good night
]

schedules_by_week_day = {
    0: default_daily_schedule,  # Monday
    1: default_daily_schedule,  # Tuesday
    2: default_daily_schedule,  # Wednesday
    3: thursday_schedule,  # Thursday
    4: default_daily_schedule,  # Friday
    5: default_daily_schedule,  # Saturday
    6: default_daily_schedule,  # Sunday
}

update_cron_job_name = 'update_boards_and_schedule_next_change'


def find_current_and_next_scheduling(schedules_by_weed_day: dict[int, List[ScheduledMessageTiming]]) \
        -> Tuple[ScheduledMessageTiming, ScheduledMessageTiming]:
    # Find current scheduledMessageTiming that should be currently active. Initiated with last timing of the day.
    weekday_today = datetime.datetime.now().weekday()
    schedule_today = schedules_by_weed_day.get(weekday_today)

    current_scheduled_index = None
    current_time = datetime.datetime.now().time()

    for (i, scheduling) in enumerate(schedule_today):
        # Find last scheduled message which starting time is before current time
        if current_time > scheduling.starting_from:
            current_scheduled_index = i

    # If none -> is carry over scheduled message from previous day
    if current_scheduled_index is None:
        weekday_yesterday = 6 if weekday_today == 0 else weekday_today - 1
        schedule_yesterday = schedules_by_weed_day.get(weekday_yesterday)
        # Current schedule is the last schedule of the previous day, next schedule is the first of the current day
        return schedule_yesterday[-1], schedules_by_weed_day.get(weekday_today)[0]
    elif current_scheduled_index == len(schedule_today) - 1:
        # Last of day. Return current and the first of the next day.
        weekday_tomorrow = 0 if weekday_today == 6 else weekday_today + 1
        return schedule_today[current_scheduled_index], schedules_by_weed_day.get(weekday_tomorrow)[0]
    else:
        # Other situations (both schedules start on the current date)
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
        self.boards: List[MessageBoard] = self._init_all_message_boards_for_chats()

    async def update_boards_and_schedule_next_update(self, context: CallbackContext = None):
        # Find current and next scheduling. Update current scheduling message to all boards and schedule next change
        # at the start of the next scheduling.
        if not self.boards:
            return  # No message boards

        current_scheduling, next_scheduling = find_current_and_next_scheduling(schedules_by_week_day)

        if current_scheduling.is_chat_specific:
            # Create chat specific message for each board and update it to the board
            for board in self.boards:
                await update_message_board_with_chat_specific_scheduling(board, current_scheduling)
        else:
            # Create message board message once and update it to each board
            await update_message_boards_with_generic_scheduling(self.boards, current_scheduling)

        self._schedule_next_update(next_scheduling)

    def find_board(self, chat_id) -> MessageBoard | None:
        for board in self.boards:
            if board.chat_id == chat_id:
                return board
        return None

    async def create_new_board(self, chat_id, message_id) -> MessageBoard:
        new_board = MessageBoard(service=self, chat_id=chat_id, host_message_id=message_id)
        self.boards.append(new_board)

        # Start board with scheduled message
        current_scheduling, next_scheduling = find_current_and_next_scheduling(schedules_by_week_day)
        if current_scheduling.is_chat_specific:
            await update_message_board_with_chat_specific_scheduling(new_board, current_scheduling)
        else:
            await update_message_boards_with_generic_scheduling([new_board], current_scheduling)
        self._schedule_next_update(next_scheduling)
        return new_board

    def remove_board_from_service_and_chat(self, board: MessageBoard):
        # Remove board from the list
        self.boards.remove(board)
        # Remove board from the database
        database.remove_message_board_from_chat(board.chat_id)

    def _init_all_message_boards_for_chats(self) -> List[MessageBoard]:
        # Initialize message board for each chat that has message board set
        boards = []
        for chat in database.get_chats_with_message_board():
            if has(chat.message_board_msg_id):
                board = MessageBoard(service=self, chat_id=chat.id, host_message_id=chat.message_board_msg_id)
                boards.append(board)
        return boards

    def _schedule_next_update(self, next_scheduling: ScheduledMessageTiming):
        # Schedule next change only if there is no update task currently scheduled
        current_update_jobs = self.application.job_queue.get_jobs_by_name(update_cron_job_name)
        if not current_update_jobs:
            # Calculate next scheduling start time and add it to the job queue to be run once
            next_scheduling_start_dt = datetime.datetime.combine(datetime.date.today(), next_scheduling.starting_from)
            self.application.job_queue.run_once(callback=self.update_boards_and_schedule_next_update,
                                                when=next_scheduling_start_dt,
                                                name=update_cron_job_name)


def find_board(chat_id) -> MessageBoard | None:
    """ Shortcut for finding message board. Contains None-check for the convenience
        of tests where message board functionality is not tested. """
    if instance:
        return instance.find_board(chat_id)


async def update_message_board_with_chat_specific_scheduling(board: MessageBoard,
                                                             current_scheduling: ScheduledMessageTiming):
    # Initializer call that creates new scheduled message
    message: MessageBoardMessage = await current_scheduling.message_provider(board, board.chat_id)
    await board.set_new_scheduled_message(message)


async def update_message_boards_with_generic_scheduling(boards: List[MessageBoard],
                                                        current_scheduling: ScheduledMessageTiming):
    # Content of the message is the same for all boards and is created only once
    message_with_preview: MessageWithPreview = await current_scheduling.message_provider()
    for board in boards:
        message_board_message = MessageBoardMessage(message_board=board,
                                                    body=message_with_preview.body,
                                                    preview=message_with_preview.preview,
                                                    parse_mode=message_with_preview.parse_mode)
        await board.set_new_scheduled_message(message_board_message)


def add_notification_if_using_message_board(chat_id: int, notification_content: str) -> None:
    """ If the chat is using message board, given text is added as a notification to the board. """
    board = find_board(chat_id)
    if board:
        notification = NotificationMessage(board, notification_content)
        board.add_notification(notification)


#
# singleton instance of this service
#
instance: MessageBoardService | None = None

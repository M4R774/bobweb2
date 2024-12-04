import datetime
import zoneinfo
from typing import List, Callable, Awaitable, Tuple

from telegram.ext import Application, ContextTypes

from bobweb.bob import main, database, command_sahko, command_ruoka, command_epic_games, good_night_wishes, \
    command_users
from bobweb.bob.activities.daily_question import daily_question_menu_states
from bobweb.bob.command_weather import create_weather_scheduled_message
from bobweb.bob.message_board import MessageBoard, MessageBoardMessage, MessageWithPreview, NotificationMessage
from bobweb.bob.resources import bob_constants
from bobweb.bob.utils_common import has


class ScheduledMessageTiming:
    """
    Represents a scheduled message timing. Contains
    - starting time without date,
    - message provider which returns the scheduled message when invoked or None, is schedule should not be used in the chat
    - whether the message is chat specific or not

    If message is chat specific, new MessageBoardMessage should be created by the message provider.
    If the schedule is not chat specific, message provider returns content of the message from which new
    ScheduledMessage is then added to all active message boards.
    """

    def __init__(self,
                 local_starting_from: datetime.time,
                 # Is either function that takes board and chat_id to produce messageBoardMessage
                 # OR is provider, that provides contents of the message from which new message is created for each chat
                 message_provider: Callable[[MessageBoard, int], Awaitable[MessageBoardMessage | None]]
                                   | Callable[[], Awaitable[MessageWithPreview]],
                 is_chat_specific: bool = False):
        self.local_starting_from = local_starting_from
        self.message_provider = message_provider
        # If scheduled message is chat specific, each message is created separately for each board and the chat id is
        # given as a parameter to the message_provider. Otherwise, the scheduled message is created only once and the
        # same result is updated to each chats message board.
        self.is_chat_specific = is_chat_specific


def create_schedule(hour: int, minute: int, message_provider: Callable[[], Awaitable[MessageWithPreview]]) \
        -> ScheduledMessageTiming:
    """
    Creates schedule for message that has same content in each chat and is not chat specific in any way.
    :param hour: staring hour in Finnish local time
    :param minute: staring minute in Finnish local time
    :param message_provider: async method which invocation produces the MessageWithPreview
    :return: Scheduled message timing
    """
    return ScheduledMessageTiming(datetime.time(hour, minute), message_provider)


def create_schedule_with_chat_context(
        hour: int, minute: int, message_provider: Callable[[MessageBoard, int], Awaitable[MessageBoardMessage | None]]) \
        -> ScheduledMessageTiming:
    """
    Creates schedule for message that is chat specific and which content is created for each chat separately.
    :param hour: staring hour in Finnish local time
    :param minute: staring minute in Finnish local time
    :param message_provider: async method which invocation produces the MessageBoardMessage
    :return: Scheduled message timing
    """
    return ScheduledMessageTiming(datetime.time(hour, minute), message_provider, is_chat_specific=True)


# Localization locale for schedules
schedule_timezone_info = zoneinfo.ZoneInfo(bob_constants.DEFAULT_TIMEZONE)

# Default schedule for the day. Note! Times are in localized Finnish Time (UTC+2 or UTC+3, depending on DST).
# Each time new update is scheduled, it is scheduled as Finnish time as stated below.
default_daily_schedule: list[ScheduledMessageTiming] = [
    create_schedule_with_chat_context(6, 0, create_weather_scheduled_message),  # Weather
    create_schedule(9, 0, command_sahko.create_message_with_preview),  # Electricity
    create_schedule(13, 0, command_ruoka.create_message_board_daily_message),  # Random receipt
    create_schedule(23, 0, good_night_wishes.create_good_night_message),  # Good night
]

thursday_schedule: list[ScheduledMessageTiming] = [
    create_schedule_with_chat_context(6, 0, create_weather_scheduled_message),  # Weather
    create_schedule(9, 0, command_sahko.create_message_with_preview),  # Electricity
    create_schedule(13, 0, command_ruoka.create_message_board_daily_message),  # Random receipt
    # Epic Games announcement
    create_schedule(16, 0, command_epic_games.create_message_board_daily_message),  # Epic Games
    create_schedule(23, 0, good_night_wishes.create_good_night_message),  # Good night
]

friday_schedule: list[ScheduledMessageTiming] = [
    create_schedule_with_chat_context(6, 0, create_weather_scheduled_message),  # Weather
    create_schedule(9, 0, command_sahko.create_message_with_preview),  # Electricity
    # 13:38 1337 scores
    create_schedule_with_chat_context(13, 38, command_users.create_message_board_msg),
    create_schedule(15, 30, command_ruoka.create_message_board_daily_message),  # Random receipt
    # 18:00 päivän kysymys score list
    create_schedule_with_chat_context(18, 0, daily_question_menu_states.create_message_board_msg),
    create_schedule(23, 0, good_night_wishes.create_good_night_message),  # Good night
]

schedules_by_week_day = {
    0: default_daily_schedule,  # Monday
    1: default_daily_schedule,  # Tuesday
    2: default_daily_schedule,  # Wednesday
    3: thursday_schedule,  # Thursday
    4: friday_schedule,  # Friday
    5: default_daily_schedule,  # Saturday
    6: default_daily_schedule,  # Sunday
}


def find_current_and_next_schedule(schedules_by_week_day: dict[int, List[ScheduledMessageTiming]]) \
        -> Tuple[ScheduledMessageTiming, datetime.datetime]:
    """
    Find scheduling that should be currently on and the next scheduling with its starting datetime.
    NOTE! The schedules are in Finnish local time as it's easier thant to keep them in UTC and then handle
    daylights savings times effect.
    :param schedules_by_week_day:
    :return: Current schedule, next schedule and next schedules starting datetime
    """
    local_datetime_now = datetime.datetime.now(tz=schedule_timezone_info)
    # Find current scheduledMessageTiming that should be currently active. Initiated with last timing of the day.
    weekday_today = local_datetime_now.weekday()  # Monday == 0 ... Sunday == 6
    todays_schedules = schedules_by_week_day.get(weekday_today)

    date_tomorrow = local_datetime_now + datetime.timedelta(days=1)

    current_scheduled_index = None
    local_current_time = datetime.datetime.now(tz=schedule_timezone_info)

    for (i, scheduling) in enumerate(todays_schedules):
        # Find last scheduled message which starting time is before current time
        if local_current_time.time() > scheduling.local_starting_from:
            current_scheduled_index = i

    # If none -> is carry over scheduled message from previous day
    if current_scheduled_index is None:
        weekday_yesterday = 6 if weekday_today == 0 else weekday_today - 1
        schedule_yesterday = schedules_by_week_day.get(weekday_yesterday)
        # Current schedule is the last schedule of the previous day, next schedule is the first of the current day
        current_schedule = schedule_yesterday[-1]
        next_schedule = schedules_by_week_day.get(weekday_today)[0]
        local_next_update_at = _combine_date_with_time(local_datetime_now, next_schedule)

    elif current_scheduled_index == len(todays_schedules) - 1:
        # Last of day. Return current and the first of the next day.
        weekday_tomorrow = 0 if weekday_today == 6 else weekday_today + 1
        current_schedule = todays_schedules[current_scheduled_index]
        next_schedule = schedules_by_week_day.get(weekday_tomorrow)[0]
        local_next_update_at = _combine_date_with_time(date_tomorrow, next_schedule)

    else:
        # Other situations (both schedules start on the current date)
        current_schedule = todays_schedules[current_scheduled_index]
        next_schedule = todays_schedules[current_scheduled_index + 1]
        local_next_update_at = _combine_date_with_time(local_datetime_now, next_schedule)

    return current_schedule, local_next_update_at


def _combine_date_with_time(date: datetime.date, next_schedule: ScheduledMessageTiming):
    return datetime.datetime.combine(date, next_schedule.local_starting_from, tzinfo=schedule_timezone_info)


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

    def find_board(self, chat_id) -> MessageBoard | None:
        for board in self.boards:
            if board.chat_id == chat_id:
                return board
        return None

    async def update_boards_and_schedule_next_update(self, context: ContextTypes.DEFAULT_TYPE = None):
        # Find current and next scheduling. Update current scheduling message to all boards and schedule next change
        # at the start of the next scheduling.
        if not self.boards:
            return  # No message boards

        next_update_at = await _update_boards_with_current_schedule_get_update_datetime(self.boards)
        self._schedule_next_update(next_update_at)

    async def create_new_board(self, chat_id, message_id):
        """
        Creates new message board, updates it and adds it to the list of boards to update.
        :param chat_id:
        :param message_id:
        :return:
        """
        new_board = MessageBoard(service=self, chat_id=chat_id, host_message_id=message_id)
        self.boards.append(new_board)

        # Now either there are other boards and update loop is already running or this is
        # the first board and starts the update loop
        next_update_at = await _update_boards_with_current_schedule_get_update_datetime([new_board])
        self._schedule_next_update(next_update_at)

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

    def _schedule_next_update(self, next_starts_at: datetime.datetime):
        # Calculate next scheduling start time and add it to the job queue to be run once
        # Scheduling is done with Finnish localized time
        self.application.job_queue.run_once(callback=self.update_boards_and_schedule_next_update,
                                            when=next_starts_at)


async def _update_boards_with_current_schedule_get_update_datetime(boards: List[MessageBoard]) -> datetime.datetime:
    """
    Updates boards with the current schedule and determines the next update datetime.
    """
    current_schedule, local_next_update_at = find_current_and_next_schedule(schedules_by_week_day)

    if current_schedule.is_chat_specific:
        # Update each board individually with chat-specific content
        for board in boards:
            await update_message_board_with_chat_specific_scheduling(board, current_schedule)
    else:
        # Update all boards with shared content
        await update_message_boards_with_generic_scheduling(boards, current_schedule)

    return local_next_update_at


def find_board(chat_id) -> MessageBoard | None:
    """ Shortcut for finding message board. Contains None-check for the convenience
        of tests where message board functionality is not tested. """
    if instance:
        return instance.find_board(chat_id)


async def update_message_board_with_chat_specific_scheduling(board: MessageBoard,
                                                             current_scheduling: ScheduledMessageTiming):
    """
    Invokes message provider and updates the message board if the message provider return value that is not None.
    Message provider can return None if schedule is disabled (temporary or permanently) or if creating scheduled message
    content fails for some reason.
    :param board: board for which message is created
    :param current_scheduling:
    :return:
    """
    # Initializer call that creates new scheduled message
    message: MessageBoardMessage | None = await current_scheduling.message_provider(board, board.chat_id)
    if message is not None:
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

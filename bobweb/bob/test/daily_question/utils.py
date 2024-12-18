import datetime
from typing import Tuple

import pytz
from freezegun.api import FrozenDateTimeFactory
from django.test import TestCase

from bobweb.bob import database
from bobweb.bob.activities.activity_state import back_button
from bobweb.bob.activities.daily_question.daily_question_menu_states import stats_btn, start_season_btn, \
    DQMainMenuState
from bobweb.bob.resources.bob_constants import ISO_DATE_FORMAT, fitz
from bobweb.bob.tests_mocks_v2 import MockChat, MockUser, init_chat_user
from bobweb.web.bobapp.models import DailyQuestionSeason


# NOTE! Datetimes are saved as UTC time to database


async def populate_season_v2(chat: MockChat, start_datetime: datetime = None) -> DailyQuestionSeason:
    if start_datetime is None:
        start_datetime = datetime.datetime.now(tz=pytz.UTC)

    user = MockUser()
    await go_to_main_menu(user=user, chat=chat)
    await user.press_button(start_season_btn)
    bots_msg = chat.bot.messages[-1]
    await user.send_message(start_datetime.strftime(ISO_DATE_FORMAT), reply_to_message=bots_msg)
    await user.send_message('season_name', reply_to_message=bots_msg)
    season = DailyQuestionSeason.objects.order_by('-id').first()
    if season is None:
        raise Exception('Error: No season created. Check if season creation process or mock-methods have been changed.')
    return season


async def populate_season_with_dq_and_answer_v2(chat: MockChat) -> DailyQuestionSeason:
    # First check if chat already has active season. If has, skip populating season
    season: DailyQuestionSeason = database.find_active_dq_season(chat.id, datetime.datetime.now(tz=fitz)).first()
    if season is None:
        season = await populate_season_v2(chat)

    user1 = MockUser(chat=chat)
    dq_message = await user1.send_message(text='#päivänkysymys dq1')

    user2 = MockUser(chat=chat)
    await user2.send_message(text='[prepopulated answer]', reply_to_message=dq_message)
    return season


async def populate_questions_with_answers_v2(chat: MockChat, dq_count: int, clock: FrozenDateTimeFactory = None):
    """
    Populates n amount of mock daily questions with single answer to each. If clock is given, advances
    time with one day between each daily question.
    """
    # Initiate only 2 users as no more is required. Question author and answer author is toggled between these two
    # I.E. first user A asks question and user B answers. Then user B asks and user A answers
    users = [MockUser(chat=chat), MockUser(chat=chat)]
    for i in range(dq_count):
        dq_author_index = i % 2
        dq_message = await users[dq_author_index].send_message(text=f'#päivänkysymys dq {i + 1}')

        answer_author_index = 1 - dq_author_index
        await users[answer_author_index].send_message(text=f'answer {i + 1}', reply_to_message=dq_message)

        if clock is not None:
            clock.tick(datetime.timedelta(days=1))


async def go_to_main_menu(user: MockUser = None, chat: MockChat = None) -> None:
    user, chat = extract_chat_and_user(user, chat)
    await user.send_message(kysymys_command, chat)
    if "Päivän kysyjät" in chat.last_bot_txt():
        await user.press_button(back_button)


async def go_to_stats_menu(user: MockUser = None, chat: MockChat = None) -> None:
    user, chat = extract_chat_and_user(user, chat)
    await user.send_message(kysymys_command, chat)  # Message from user
    if DQMainMenuState._menu_text not in chat.last_bot_txt():
        await user.press_button(back_button)
    await user.press_button(stats_btn)  # User presses button with label


def extract_chat_and_user(user: MockUser = None, chat: MockChat = None) -> Tuple[MockUser, MockChat]:
    if user is None and chat is None:
        raise Exception('give user or chat')
    if user is None:
        user = MockUser()
        user.chats.append(chat)
    if chat is None:
        chat = user.chats[-1]
    return user, chat


# Reply should be strictly equal to expected text
async def assert_reply_equal(test: TestCase, message_text: str, expected: str):
    """
    :param test: TestCase which assertEqual method is called
    :param message_text: message that is sent in a chat that bot is a member
    :param expected: expected reply from the bot. Strict equality is used
    :return:
    """
    chat, user = init_chat_user()
    await user.send_message(message_text)
    test.assertEqual(expected, chat.last_bot_txt())


# constants
kysymys_command = '/kysymys'
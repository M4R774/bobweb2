import datetime

import pytz

from bobweb.bob.resources.bob_constants import ISO_DATE_FORMAT
from bobweb.bob.tests_mocks_v1 import MockMessage as MockMessage_v1
from bobweb.bob.tests_mocks_v2 import MockChat, MockUser
from bobweb.bob.tests_utils import MockUpdate, get_latest_active_activity
from bobweb.web.bobapp.models import DailyQuestionSeason


# NOTE! Datetimes are saved as UTC time to database


def populate_season_v2(chat: MockChat, start_datetime: datetime = None) -> DailyQuestionSeason:
    if start_datetime is None:
        start_datetime = datetime.datetime.now(tz=pytz.UTC)

    user = MockUser()
    user.send_update(kysymys_command, chat=chat)
    user.press_button('Kausi')
    user.press_button('Aloita kausi')
    bots_msg = chat.bot.messages[-1]
    user.send_update(start_datetime.strftime(ISO_DATE_FORMAT), reply_to_message=bots_msg)
    user.send_update('season_name', reply_to_message=bots_msg)
    season = DailyQuestionSeason.objects.order_by('-id').first()
    if season is None:
        raise Exception('Error: No season created. Check if season creation process or mock-methods have been changed.')
    return season


def populate_season_with_dq_and_answer_v2(chat: MockChat):
    season = populate_season_v2(chat)

    user = MockUser()
    dq_message = user.send_update(text='#päivänkysymys dq1', chat=chat)

    user = MockUser()
    user.send_update(text='[prepopulated answer]', reply_to_message=dq_message, chat=chat)
    return season


def go_to_seasons_menu_v2(user: MockUser = None, chat: MockChat = None) -> None:
    if user is None and chat is None:
        raise Exception('give user or chat')
    elif user is None and chat is not None:
        user = MockUser()
        user.chats.append(chat)
    elif chat is None:
        chat = user.chats[-1]
    user.send_update(kysymys_command, chat)  # Message from user
    user.press_button('Kausi')  # User presses button with label


def start_create_season_activity_get_host_message(update: MockUpdate) -> MockMessage_v1:
    update.send_text(kysymys_command)  # Message from user
    update.press_button('Kausi')  # User presses button with label
    update.press_button('Aloita kausi')
    host_message = get_latest_active_activity().host_message
    return host_message


# constants
kysymys_command = '/kysymys'
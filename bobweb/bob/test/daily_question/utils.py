import datetime

import pytz

from bobweb.bob.resources.bob_constants import ISO_DATE_FORMAT
from bobweb.bob.tests_mocks_v1 import MockMessage as MockMessage_v1
from bobweb.bob.tests_mocks_v2 import MockChat, MockUser, MockMessage
from bobweb.bob.utils_common import has_no
from bobweb.bob.tests_utils import MockUpdate, get_latest_active_activity
from bobweb.web.bobapp.models import Chat, DailyQuestionSeason, TelegramUser, DailyQuestion, DailyQuestionAnswer

# NOTE! Datetimes are saved as UTC time to database

def populate_season() -> DailyQuestionSeason:
    Chat.objects.create(id=1337, title="chat")
    chat = Chat.objects.get(id=1337)
    season_created = datetime.datetime(2022, 1, 1, 10, 5, tzinfo=pytz.UTC)
    DailyQuestionSeason.objects.create(id=1, chat=chat, season_name="1", start_datetime=season_created)
    return DailyQuestionSeason.objects.get(id=1)


def populate_season_v2(chat: MockChat, start_datetime: datetime = None) -> DailyQuestionSeason:
    if start_datetime is None:
        start_datetime = datetime.datetime.now(tz=pytz.UTC)

    user = MockUser()
    user.send_update('/kysymys', chat=chat)
    user.press_button('Kausi')
    user.press_button('Aloita kausi')
    bots_msg = chat.bot.messages[-1]
    user.send_update(start_datetime.strftime(ISO_DATE_FORMAT), reply_to_message=bots_msg)
    user.send_update('season_name', reply_to_message=bots_msg)
    season = DailyQuestionSeason.objects.order_by('-id').first()
    if season is None:
        raise Exception('Error: No season created. Check if season creation process or mock-methods have been changed.')
    return season


def populate_season_with_dq_and_answer():
    season = populate_season()
    TelegramUser.objects.create(id=1, username='1')
    user1 = TelegramUser.objects.get(id=1)
    TelegramUser.objects.create(id=2, username='2')
    user2 = TelegramUser.objects.get(id=2)
    DailyQuestion.objects.create(id=1,
                                 season=season,
                                 created_at=datetime.datetime(2022, 1, 2, 10, 0, tzinfo=pytz.UTC),
                                 date_of_question=datetime.datetime(2022, 1, 2, 0, 0, tzinfo=pytz.UTC),
                                 message_id=1,
                                 question_author=user1,
                                 content='#päivänkysymys dq1')
    dq = DailyQuestion.objects.get(id=1)
    DailyQuestionAnswer.objects.create(id=1,
                                       question=dq,
                                       created_at=datetime.datetime(2022, 1, 3, 11, 11, tzinfo=pytz.UTC),
                                       message_id=2,
                                       answer_author=user2,
                                       content="a1",
                                       is_winning_answer=False)
    DailyQuestionAnswer.objects.get(id=1)


def populate_season_with_dq_and_answer_v2(chat: MockChat):
    season = populate_season_v2(chat)

    user = MockUser()
    dq_message = user.send_update(text='#päivänkysymys dq1', chat=chat)

    user = MockUser()
    user.send_update(text='[prepopulated answer]', reply_to_message=dq_message, chat=chat)
    return season


def go_to_seasons_menu_get_host_message(update: MockUpdate = None) -> MockMessage_v1:
    if has_no(update):
        update = MockUpdate()
    update = update.send_text('/kysymys')  # Message from user
    update.press_button('Kausi')  # User presses button with label
    # Get the only activity's host message
    host_message = get_latest_active_activity().host_message
    return host_message


def go_to_seasons_menu_v2(user: MockUser = None, chat: MockChat = None) -> None:
    if user is None and chat is None:
        raise Exception('give user or chat')
    if user is None:
        user = MockUser()
    if chat is None:
        chat = user.chats[-1]
    user.send_update('/kysymys', chat)  # Message from user
    user.press_button('Kausi')  # User presses button with label


def start_create_season_activity_get_host_message(update: MockUpdate) -> MockMessage_v1:
    update.send_text('/kysymys')  # Message from user
    update.press_button('Kausi')  # User presses button with label
    update.press_button('Aloita kausi')
    host_message = get_latest_active_activity().host_message
    return host_message

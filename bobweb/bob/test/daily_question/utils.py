import datetime

from bobweb.bob.utils_common import has_no
from bobweb.bob.utils_test import MockUpdate, get_latest_active_activity, MockMessage
from bobweb.web.bobapp.models import Chat, DailyQuestionSeason, TelegramUser, DailyQuestion, DailyQuestionAnswer


def populate_season() -> DailyQuestionSeason:
    Chat.objects.create(id=1337, title="chat")
    chat = Chat.objects.get(id=1337)
    season_created = datetime.datetime(2022, 1, 1, 10, 5)
    DailyQuestionSeason.objects.create(id=1, chat=chat, season_name="1", start_datetime=season_created)
    return DailyQuestionSeason.objects.get(id=1)


def populate_season_with_dq_and_answer():
    season = populate_season()
    TelegramUser.objects.create(id=1, username='1')
    user1 = TelegramUser.objects.get(id=1)
    TelegramUser.objects.create(id=2, username='2')
    user2 = TelegramUser.objects.get(id=2)
    DailyQuestion.objects.create(id=1,
                                 season=season,
                                 created_at=datetime.datetime(2022, 1, 2, 10, 10),
                                 date_of_question=datetime.datetime(2022, 1, 2, 0, 0),
                                 message_id=1,
                                 question_author=user1,
                                 content='dq1')
    dq = DailyQuestion.objects.get(id=1)
    DailyQuestionAnswer.objects.create(id=1,
                                       question=dq,
                                       created_at=datetime.datetime(2022, 1, 3, 11, 11),
                                       message_id=2,
                                       answer_author=user2,
                                       content="a1",
                                       is_winning_answer=False)
    dq_answer = DailyQuestionAnswer.objects.get(id=1)


def go_to_seasons_menu_get_host_message(update: MockUpdate = None) -> MockMessage:
    if has_no(update):
        update = MockUpdate()
    update = update.send_text('/kysymys')  # Message from user
    update.press_button('Kausi')  # User presses button with label
    # Get the only activity's host message
    host_message = get_latest_active_activity().host_message
    return host_message


def start_create_season_activity_get_host_message(update: MockUpdate) -> MockMessage:
    update.send_text('/kysymys')  # Message from user
    update.press_button('Kausi')  # User presses button with label
    update.press_button('Aloita kausi')
    host_message = get_latest_active_activity().host_message
    update.effective_message.reply_to_message = host_message
    return host_message

import datetime
from unittest.mock import MagicMock

from django.test import TestCase
from telegram import User

from bobweb.bob.utils_common import has_no
from bobweb.bob.utils_test import MockUpdate, get_latest_active_activity, MockMessage
from bobweb.web.bobapp.models import Chat, DailyQuestionSeason, TelegramUser, DailyQuestion, DailyQuestionAnswer


def populate_season_with_dq_and_answer(test_case: TestCase):
    Chat.objects.create(id=1337, title="chat")
    test_case.chat = Chat.objects.get(id=1337)
    season_created = datetime.datetime(2022, 1, 1, 10, 5)
    DailyQuestionSeason.objects.create(id=1, chat=test_case.chat, season_name="1", start_datetime=season_created)
    test_case.season = DailyQuestionSeason.objects.get(id=1)
    TelegramUser.objects.create(id=1, username='1')
    test_case.user1 = TelegramUser.objects.get(id=1)
    TelegramUser.objects.create(id=2, username='2')
    test_case.user2 = TelegramUser.objects.get(id=2)
    DailyQuestion.objects.create(id=1,
                                 season=test_case.season,
                                 created_at=datetime.datetime(2022, 1, 2, 10, 10),
                                 date_of_question=datetime.datetime(2022, 1, 2, 0, 0),
                                 message_id=1,
                                 question_author=test_case.user1,
                                 content='dq1')
    test_case.dq = DailyQuestion.objects.get(id=1)
    DailyQuestionAnswer.objects.create(id=1,
                                       question=test_case.dq,
                                       created_at=datetime.datetime(2022, 1, 3, 11, 11),
                                       message_id=2,
                                       answer_author=test_case.user2,
                                       content="a1",
                                       is_winning_answer=False)
    test_case.dq_answer = DailyQuestionAnswer.objects.get(id=1)


def go_to_seasons_menu_get_host_message(update: MockUpdate = None) -> MockMessage:
    if has_no(update):
        update = MockUpdate()
    update = update.send_text('/kysymys')  # Message from user
    update.press_button('Kausi')  # User presses button with label
    # Get the only activity's host message
    host_message = get_latest_active_activity().host_message
    host_message.from_user = MagicMock(spec=User)
    return host_message


def start_create_season_activity_get_host_message(update: MockUpdate) -> MockMessage:
    update.send_text('/kysymys')  # Message from user
    update.press_button('Kausi')  # User presses button with label
    update.press_button('Aloita kausi')
    host_message = get_latest_active_activity().host_message
    update.effective_message.reply_to_message = host_message
    host_message.from_user = MagicMock(spec=User)
    return host_message

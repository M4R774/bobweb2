import os

import django
from django.test import TestCase


class DailyQuestionTestSuite(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuite, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    # #
    # # Daily Questions
    # #
    # def test_when_no_season_defined_should_ask_for_season_information(self):
    #     raise NotImplementedError()
    #
    # def test_when_given_season_creates_season_and_question(self):
    #     raise NotImplementedError()
    #
    # def test_when_chat_has_season_question_is_saved(self):
    #     raise NotImplementedError()
    #
    # def test_when_question_is_saved_its_sender_is_set_as_prev_question_winner(self):
    #     raise NotImplementedError()
    #
    # def test_when_not_weekday_gives_error(self):
    #     raise NotImplementedError()
    #
    # def test_when_daily_question_allready_created_gives_error(self):
    #     raise NotImplementedError()
    #
    # def test_reply_to_question_message_raises_reply_count(self):
    #     raise NotImplementedError()
    #


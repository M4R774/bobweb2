import os

import django
from django.test import TestCase

from bobweb.bob.test.daily_question.utils import populate_season
from bobweb.bob.utils_test import MockUpdate
from bobweb.web.bobapp.models import DailyQuestion


class DailyQuestionTestSuite(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuite, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    #
    # Daily Questions
    #
    def test_when_chat_has_season_question_is_saved(self):
        populate_season()
        MockUpdate().send_text("#päivänkysymys kuka?")
        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)



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


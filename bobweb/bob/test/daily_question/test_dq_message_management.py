import os
from bobweb.bob import main
import django
from django.test import TestCase

from bobweb.bob.test.daily_question.utils import populate_season, populate_season_with_dq_and_answer
from bobweb.bob.utils_test import MockUpdate, MockMessage
from bobweb.web.bobapp.models import DailyQuestion, TelegramUser, DailyQuestionAnswer, Chat


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

    def test_reply_to_daily_question_is_saved_as_answer(self):
        populate_season_with_dq_and_answer()
        TelegramUser.objects.create(id=3, username='3')

        user3 = TelegramUser.objects.get(id=3)
        chat = Chat.objects.get(id=1337)
        message = MockMessage(chat)
        message.from_user = user3
        update = MockUpdate(message)
        update.effective_user = user3
        mock_dq_message = MockMessage(chat)
        mock_dq_message.message_id = 1
        update.effective_message.reply_to_message = mock_dq_message
        update.send_text("a3")

        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=3))
        self.assertEqual(1, len(answers))
        self.assertEqual('a3', answers[0].content)


    def test_when_question_is_saved_its_sender_is_set_as_prev_question_winner(self):
        # Unless it's the first question of the season
        populate_season_with_dq_and_answer()

        # Check that user's '2' answer is not marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=2))
        self.assertFalse(answers[0].is_winning_answer)

        user2 = TelegramUser.objects.get(id=2)
        chat = Chat.objects.get(id=1337)
        message = MockMessage(chat)
        message.from_user = user2
        update = MockUpdate(message)
        update.effective_user = user2
        update.send_text("#päivänkysymys kuka?")

        # Check that user's '2' reply to the daily question has been marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=2))
        self.assertTrue(answers[0].is_winning_answer)



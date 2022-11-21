import os
import django
from django.test import TestCase

from bobweb.bob.test.daily_question.utils import populate_season, populate_season_with_dq_and_answer
from bobweb.bob.tests_utils import MockUpdate, MockMessage, assert_has_reply_to, assert_no_reply_to
from bobweb.web.bobapp.models import DailyQuestion, TelegramUser, DailyQuestionAnswer, Chat


class DailyQuestionTestSuite(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuite, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    def test_should_reply_when_question_hashtag_anywhere_in_text(self):
        assert_has_reply_to(self, "#päivänkysymys")
        assert_has_reply_to(self, "asd\nasd #päivänkysymys")
        assert_has_reply_to(self, "#päivänkysymys asd\nasd")
        assert_has_reply_to(self, "asd\nasd #päivänkysymys asd\nasd")

    def test_no_prefix_no_reply_to_question_text_without_hashtag(self):
        assert_no_reply_to(self, "päivänkysymys")
        assert_no_reply_to(self, "/päivänkysymys")
        assert_no_reply_to(self, "/päivänkys")

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

        chat = Chat.objects.get(id=1337)
        user3 = TelegramUser.objects.get(id=3)
        mock_dq_message = MockMessage(chat)
        mock_dq_message.message_id = 1
        message = MockMessage(chat)
        message.from_user = user3
        update = MockUpdate(message)
        update.effective_user = user3
        update.effective_message.reply_to_message = mock_dq_message
        update.send_text("a3")

        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=3))
        self.assertEqual(1, len(answers))
        self.assertEqual('a3', answers[0].content)

    def test_edit_to_answer_updates_its_content(self):
        populate_season_with_dq_and_answer()

        chat = Chat.objects.get(id=1337)
        user2 = TelegramUser.objects.get(id=2)
        mock_dq_message = MockMessage(chat)
        mock_dq_message.message_id = 1

        edit_message = MockMessage(chat)
        edit_message.from_user = user2
        edit_message.message_id = 2
        edit_message.reply_to_message = mock_dq_message
        edit_update = MockUpdate(edit_message)
        edit_update.effective_user = user2
        edit_update.edit_message('a1 (edited)')

        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=2))
        self.assertEqual(1, len(answers))
        self.assertEqual('a1 (edited)', answers[0].content)

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

    def test_editing_hashtag_to_message_creates_new_daily_question(self):
        populate_season()
        update = MockUpdate(edited_message=MockMessage()).edit_message("#päivänkysymys kuka?")

        expected_reply = "Päivän kysymys tallennettu jälkikäteen lisätyn '#päivänkysymys' tägin myötä"
        self.assertRegex(update.effective_message.reply_message_text, expected_reply)

        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)

    def test_editing_saved_daily_question_updates_saved_content(self):
        populate_season_with_dq_and_answer()
        dq = DailyQuestion.objects.filter().first()
        self.assertEqual('#päivänkysymys dq1', dq.content)

        update = MockUpdate(edited_message=MockMessage())
        update.effective_message.message_id = 1
        update.edit_message("#päivänkysymys (edited)")
        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys (edited)', daily_questions[0].content)

    def test_same_user_sending_dq_as_last_one_gives_error(self):
        populate_season_with_dq_and_answer()
        update = MockUpdate()
        user1 = TelegramUser.objects.get(id=1)
        update.effective_user = user1
        update.send_text("#päivänkysymys dq2")
        expected_reply = 'Päivän kysyjä on sama kuin aktiivisen kauden edellisessä kysymyksessä. ' \
                         'Kysymystä ei tallennetu.'
        self.assertEqual(expected_reply, update.effective_message.reply_message_text)

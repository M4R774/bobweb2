import datetime
import os

import django
import pytz
from django.test import TestCase
from freezegun import freeze_time

from bobweb.bob.activities.daily_question.message_utils import dq_created_from_msg_edit
from bobweb.bob.test.daily_question.utils import populate_season_v2, populate_season_with_dq_and_answer_v2
from bobweb.bob.tests_mocks_v2 import MockMessage, MockChat, MockUser
from bobweb.bob.tests_utils import assert_has_reply_to, assert_no_reply_to
from bobweb.web.bobapp.models import DailyQuestion, DailyQuestionAnswer


@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
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

    def test_when_chat_has_season_question_is_saved_v2(self):
        chat = MockChat()
        populate_season_v2(chat, start_datetime=datetime.datetime(2022, 1, 1, tzinfo=pytz.UTC))
        user = MockUser()

        user.send_update("#päivänkysymys kuka?", chat=chat)

        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)

    def test_reply_to_daily_question_is_saved_as_answer_v2(self):
        chat = MockChat()
        user = MockUser()
        populate_season_with_dq_and_answer_v2(chat)
        dq = DailyQuestion.objects.order_by('-id').first()

        mock_dq_msg = MockMessage(chat, from_user=dq.question_author, message_id=dq.message_id)
        user.send_update('a2', chat=chat, reply_to_message=mock_dq_msg)

        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertEqual(1, len(answers))
        self.assertEqual('a2', answers[0].content)

    def test_edit_to_answer_updates_its_content_v2(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)
        dq = DailyQuestion.objects.order_by('-id').first()

        # send answer that is reply to mocked dq message
        mock_dq_msg = MockMessage(chat, from_user=dq.question_author, message_id=dq.message_id)

        user = MockUser()
        answer = user.send_update('a', chat=chat, reply_to_message=mock_dq_msg)

        # edit previous message. After this should be updated in the database
        answer.edit_message('a (edited)')

        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertEqual(1, len(answers))
        self.assertEqual('a (edited)', answers[0].content)

    def test_when_question_is_saved_its_sender_is_set_as_prev_question_winner_v2(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)

        # Check that no answer is marked as winning one
        winning_answers = list(DailyQuestionAnswer.objects.filter(is_winning_answer=True))
        self.assertEqual(0, len(winning_answers))

        # get prepopulated user, that has answered prepopulated dq in populate method (last new user in chat)
        user = chat.users[-1]
        user.send_update("#päivänkysymys kuka?", chat=chat)

        # Check that user's reply to the daily question has been marked as winning one
        winning_answers = list(DailyQuestionAnswer.objects.filter(is_winning_answer=True))
        self.assertEqual(1, len(winning_answers))
        self.assertEqual(user.id, winning_answers[-1].answer_author.id)

    def test_editing_hashtag_to_message_creates_new_daily_question_v2(self):
        chat = MockChat()
        populate_season_v2(chat)
        user = MockUser()
        message = user.send_update("kuka?", chat=chat)
        message.edit_message("#päivänkysymys kuka?")

        self.assertEqual(dq_created_from_msg_edit(False), chat.bot.messages[-1].text)

        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)

    def test_editing_saved_daily_question_updates_saved_content_v2(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)
        dq = DailyQuestion.objects.filter().first()
        self.assertEqual('#päivänkysymys dq1', dq.content)

        # send answer that is reply to mocked dq message
        mock_dq_msg = MockMessage(chat, from_user=dq.question_author, message_id=dq.message_id)
        mock_dq_msg.edit_message("#päivänkysymys (edited)")
        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys (edited)', daily_questions[0].content)

    @freeze_time('2023-01-02', as_kwarg='clock')
    def test_same_user_sending_dq_as_last_one_gives_error_v2(self, clock):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)

        clock.tick(datetime.timedelta(days=1))  # Move test logic time one day forward
        user = chat.users[1]
        user.send_update("#päivänkysymys dq2", chat=chat)

        expected_reply = 'Päivän kysyjä on sama kuin aktiivisen kauden edellisessä kysymyksessä. ' \
                         'Kysymystä ei tallennetu.'
        self.assertEqual(expected_reply, chat.bot.messages[-1].text)

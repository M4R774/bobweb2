import os

import django
from freezegun import freeze_time

from bobweb.bob import main  # needed to not cause circular import
from django.test import TestCase

from bobweb.bob.command_daily_question import target_msg_saved_as_winning_answer_msg, target_msg_saved_as_answer_msg, \
    MarkAnswerCommand
from bobweb.bob.test.daily_question.test_dq_questions_and_answers import \
    assert_winner_not_set_no_answer_to_last_dq_from_author
from bobweb.bob.test.daily_question.utils import populate_season_with_dq_and_answer_v2
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUser
from bobweb.bob.tests_utils import assert_command_triggers
from bobweb.web.bobapp.models import DailyQuestionAnswer


answer_command_msg = '/vastaus'


@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
class DailyQuestionTestSuiteV2(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuiteV2, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    def test_command_triggers(self):
        should_trigger = [answer_command_msg, '!vastaus', '.vastaus', answer_command_msg.capitalize()]
        should_not_trigger = ['vastaus', 'test /vastaus', '/vastaus test']
        assert_command_triggers(self, MarkAnswerCommand, should_trigger, should_not_trigger)


    def test_message_is_saved_as_answer_when_replied_with_mark_command(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        self.assertEqual(1, DailyQuestionAnswer.objects.count())

        user = MockUser(chat=chat)
        answer_to_be_marked = user.send_message('answer to dq')
        self.assertEqual(1, DailyQuestionAnswer.objects.count())

        user.send_message(answer_command_msg, reply_to_message=answer_to_be_marked)
        self.assertIn(target_msg_saved_as_answer_msg, chat.last_bot_txt())
        self.assertEqual(2, DailyQuestionAnswer.objects.count())

    def test_gives_notification_if_target_message_already_saved_as_answer(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)

        last_answer_msg = chat.last_user_msg()
        user.send_message(answer_command_msg, reply_to_message=last_answer_msg)
        self.assertIn('Kohdeviesti on jo tallennettu aiemmin vastaukseksi.', chat.last_bot_txt())

    def test_message_is_saved_as_answer_to_last_dq_from_its_date_when_marked(self):
        chat, user1 = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)

        answer_to_be_marked = user1.send_message('answer to dq')
        self.assertEqual(1, DailyQuestionAnswer.objects.count())

        user2 = chat.users[0]  # user with prepopulated message
        user2.send_message('#päivänkysymys new question')

        # Now we want to mark answer that is intended to the non-last dq
        user1.send_message(answer_command_msg, reply_to_message=answer_to_be_marked)
        self.assertIn(target_msg_saved_as_answer_msg, chat.last_bot_txt())
        self.assertEqual(2, DailyQuestionAnswer.objects.count())

        # In addition, check that the marked answers target dq is the right one
        target_dq = DailyQuestionAnswer.objects.filter(message_id=answer_to_be_marked.message_id).first().question
        self.assertEqual('#päivänkysymys dq1', target_dq.content)

    def test_when_answer_is_marked_if_user_is_author_of_next_question_the_question_is_set_as_winning_one(self):
        chat, user = init_chat_user()
        assert_winner_not_set_no_answer_to_last_dq_from_author(self, chat, user)
        # So now user has sent new dq and been informed, that their answer was not saved as winning one (no answer)
        message_to_mark = user.messages[0]
        user.send_message(answer_command_msg, reply_to_message=message_to_mark)
        self.assertEqual(target_msg_saved_as_winning_answer_msg, chat.last_bot_txt())
        users_answer = DailyQuestionAnswer.objects.filter(answer_author__id=user.id).first()
        self.assertTrue(users_answer.is_winning_answer)

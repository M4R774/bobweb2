import datetime
import os

import django
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory

from bobweb.bob import main  # needed to not cause circular import
from django.test import TestCase

from bobweb.bob.activities.daily_question.add_missing_answer_state import message_saved_no_answer_to_last_dq
from bobweb.bob.command_daily_question import target_msg_saved_as_winning_answer_msg, target_msg_saved_as_answer_msg, \
    MarkAnswerCommand
from bobweb.bob.test.daily_question.test_dq_questions_and_answers import assert_there_are_no_winning_answers
from bobweb.bob.test.daily_question.utils import populate_season_with_dq_and_answer_v2, populate_season_v2, \
    populate_questions_with_answers_v2
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUser, MockChat
from bobweb.bob.tests_utils import assert_command_triggers
from bobweb.web.bobapp.models import DailyQuestionAnswer


answer_command_msg = '/vastaus'


@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
class MarkAnswerCommandTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(MarkAnswerCommandTests, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    def test_command_triggers(self):
        should_trigger = [answer_command_msg, '!vastaus', '.vastaus', answer_command_msg.capitalize()]
        should_not_trigger = ['vastaus', 'test /vastaus', '/vastaus test']
        assert_command_triggers(self, MarkAnswerCommand, should_trigger, should_not_trigger)

    def test_message_without_reply_target_triggers_info_message(self):
        chat, user = init_chat_user()
        user.send_message(answer_command_msg)
        self.assertIn('Ei kohdeviestiä, mitä merkata vastaukseksi.', chat.last_bot_txt())

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
        self.assertIn('Kohdeviesti on jo tallennettu aiemmin vastaukseksi', chat.last_bot_txt())

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
        populate_season_with_dq_and_answer_v2(chat)
        user.send_message('users answer, but not reply to dq, so not saved as answer')

        # user has not answered prepopulated daily question. Should give error when trying to set winner
        user.send_message('#päivänkysymys should notify author not set winner as no answer to last dq')
        self.assertIn(message_saved_no_answer_to_last_dq, chat.bot.messages[-1].text)
        assert_there_are_no_winning_answers(self)

        # So now user has sent new dq and been informed, that their answer was not saved as winning one (no answer)
        message_to_mark = user.messages[0]
        user.send_message(answer_command_msg, reply_to_message=message_to_mark)
        self.assertEqual(target_msg_saved_as_winning_answer_msg, chat.last_bot_txt())
        users_answer = DailyQuestionAnswer.objects.filter(answer_author__id=user.id).first()
        self.assertTrue(users_answer.is_winning_answer)

    @freeze_time('2023-01-02', as_kwarg='clock')
    def test_marking_old_answer_should_set_as_winning_one(self, clock: FrozenDateTimeFactory):
        chat = MockChat()
        userA = MockUser(chat=chat)
        userB = MockUser(chat=chat)
        userC = MockUser(chat=chat)

        populate_season_v2(chat)
        populate_questions_with_answers_v2(chat, 3, clock)
        last_dq_msg = chat.last_user_msg()
        userA.send_message('answer', reply_to_message=last_dq_msg)

        clock.tick(datetime.timedelta(days=1))

        dq = userA.send_message('#päivänkysymys testing that mark answer is working')

        clock.tick(datetime.timedelta(hours=1))
        # Now, userB sends message that was ment to be answer but was not sent as a reply
        non_reply_answer = userB.send_message('this should have been a reply to dq')

        clock.tick(datetime.timedelta(hours=1))
        userC.send_message('userC answer correctly as a reply', reply_to_message=dq)

        # As this test tries to mock real situation, userA now informs that userB has won
        userA.send_message('Congratulations! UserB won!')

        # Tick one day forward
        clock.tick(datetime.timedelta(days=1))

        # Now userB sends new daily question
        userB.send_message('#päivänkysymys this should trigger no-answer-set error')

        self.assertIn(message_saved_no_answer_to_last_dq, chat.bot.messages[-1].text)

        # UserC now notices this and marks userB's answer
        # Different user on purpose to make sure it does not matter who sends the marking answer
        userC.send_message(answer_command_msg, reply_to_message=non_reply_answer)

        # Now bot should inform that the answer has been saved and the answer set as winning one
        self.assertEqual(target_msg_saved_as_winning_answer_msg, chat.last_bot_txt())
        users_answer = DailyQuestionAnswer.objects.filter(answer_author__id=userB.id).first()
        self.assertTrue(users_answer.is_winning_answer)

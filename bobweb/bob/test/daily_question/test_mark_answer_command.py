import os

import django
from freezegun import freeze_time

from bobweb.bob import main  # needed to not cause circular import
from django.test import TestCase

from bobweb.bob.command_daily_question import MarkAnswerCommand
from bobweb.bob.test.daily_question.utils import populate_season_with_dq_and_answer_v2
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUser
from bobweb.bob.tests_utils import assert_has_reply_to, assert_get_parameters_returns_expected_value, assert_no_reply_to
from bobweb.web.bobapp.models import DailyQuestionAnswer

@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
class DailyQuestionTestSuiteV2(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuiteV2, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    def test_should_reply_to_question_commands_case_insenstivite_all_prefixes(self):
        assert_has_reply_to(self, "/vastaus")
        assert_has_reply_to(self, "!VAStaus")
        assert_has_reply_to(self, ".vastaus")
        assert_no_reply_to(self, ".vastaus 2000-01-01")
        assert_no_reply_to(self, "asd .vastaus")

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!vastaus', MarkAnswerCommand())

    def test_message_is_saved_as_answer_when_replied_with_mark_command(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        self.assertEqual(1, DailyQuestionAnswer.objects.count())

        user = MockUser(chat=chat)
        answer_to_be_marked = user.send_update('answer to dq')
        self.assertEqual(1, DailyQuestionAnswer.objects.count())

        user.send_update('/vastaus', reply_to_message=answer_to_be_marked)
        self.assertIn('Kohdeviesti tallennettu onnistuneesti vastauksena kysymykseen!', chat.last_bot_txt())
        self.assertEqual(2, DailyQuestionAnswer.objects.count())

    def test_gives_notification_if_target_message_already_saved_as_answer(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)

        last_answer_msg = chat.last_user_msg()
        user.send_update('/vastaus', reply_to_message=last_answer_msg)
        self.assertIn('Kohdeviesti on jo tallennettu aiemmin.', chat.last_bot_txt())

    def test_message_is_saved_as_answer_to_last_dq_from_its_date_when_marked(self):
        chat, user1 = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)

        answer_to_be_marked = user1.send_update('answer to dq')
        self.assertEqual(1, DailyQuestionAnswer.objects.count())

        user2 = chat.users[-1]  # user with prepopulated message
        user2.send_update('#päivänkysymys new question')

        # Now we want to mark answer that is intended to the non-last dq
        user1.send_update('/vastaus', reply_to_message=answer_to_be_marked)
        self.assertIn('Kohdeviesti tallennettu onnistuneesti vastauksena kysymykseen!', chat.last_bot_txt())
        self.assertEqual(2, DailyQuestionAnswer.objects.count())

        # In addition, check that the marked answers target dq is the right one
        target_dq = DailyQuestionAnswer.objects.filter(message_id=answer_to_be_marked.message_id).first().question
        self.assertEqual('#päivänkysymys dq1', target_dq.content)

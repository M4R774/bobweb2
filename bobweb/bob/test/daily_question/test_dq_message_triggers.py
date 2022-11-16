import os
from bobweb.bob import main
import django
from django.test import TestCase

from bobweb.bob.command_daily_question import DailyQuestionCommand
from bobweb.bob.utils_test import assert_has_reply_to, assert_no_reply_to, assert_get_parameters_returns_expected_value


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

    def test_should_reply_to_question_commands_case_insenstivite_all_prefixes(self):
        assert_has_reply_to(self, "/kysymys")
        assert_has_reply_to(self, "!KYSymys")
        assert_has_reply_to(self, ".kysymys kausi")

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!kysymys', DailyQuestionCommand())

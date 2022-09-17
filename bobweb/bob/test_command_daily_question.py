import os
from unittest import IsolatedAsyncioTestCase, mock

import main
from unittest import TestCase

import message_handler
from resources.bob_constants import PREFIXES_MATCHER
from test_main import MockUpdate

from utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_contains


class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python ../web/manage.py migrate")

    def test_command_should_reply_when_anywhere_in_text(self):
        assert_has_reply_to(self, "#päivänkysymys")
        assert_has_reply_to(self, "asd\nasd #päivänkysymys")
        assert_has_reply_to(self, "#päivänkysymys asd\nasd")
        assert_has_reply_to(self, "asd\nasd #päivänkysymys asd\nasd")

    def test_no_prefix_no_reply_without_hashtag(self):
        assert_no_reply_to(self, "päivänkysymys")
        assert_no_reply_to(self, "/päivänkysymys")
        assert_no_reply_to(self, "/päivänkys")

    #
    # Daily Question Seasons
    #
    def test_when_given_start_season_command_creates_season(self):
        raise NotImplementedError()

    def test_when_given_start_season_command_with_missing_info_gives_error(self):
        raise NotImplementedError()

    def test_when_new_season_overlaps_another_season_gives_error(self):
        raise NotImplementedError()

    def test_when_given_end_season_command_should_add_current_date_as_end(self):
        raise NotImplementedError()

    def test_when_given_end_season_command_with_date_adds_that_as_end(self):
        raise NotImplementedError()

    def test_when_given_end_season_command_gives_season_summary(self):
        raise NotImplementedError()

    #
    # Daily Questions
    #
    def test_when_no_season_defined_should_ask_for_season_information(self):
        raise NotImplementedError()

    def test_when_given_season_creates_season_and_question(self):
        raise NotImplementedError()

    def test_when_chat_has_season_question_is_saved(self):
        raise NotImplementedError()

    def test_when_question_is_saved_its_sender_is_set_as_prev_question_winner(self):
        raise NotImplementedError()

    def test_when_not_weekday_gives_error(self):
        raise NotImplementedError()

    def test_when_daily_question_allready_created_gives_error(self):
        raise NotImplementedError()

    def test_reply_to_question_message_raises_reply_count(self):
        raise NotImplementedError()

    #
    # Daily Question Commands
    #
    def test_when_reply_to_message_with_command_overrides_it_as_daily_question(self):
        # Kun mihinkä vaan viestiin vastataan ja viesti sisältää komennon /kysymys tänään
        # Niin vanha päivänkysymys poistetaan ja replyn kohteena oleva viesti lisätään
        # sen päivän kysymykseksi
        raise NotImplementedError()

    def test_when_reply_to_message_with_command_overrides_prev_question_winner(self):
        # Sama kuin yllä, mutta edellisen päivän voittaja vaihdetaan
        raise NotImplementedError()

    def test_command_kysymys_tanaan_gives_season_summary(self):
        raise NotImplementedError()

    def test_command_kysymys_with_date_gives_that_date_summary(self):
        raise NotImplementedError()

    def test_command_with_invalid_date_gives_error(self):
        # Paramter is malformed or no question recorded on that day
        raise NotImplementedError()

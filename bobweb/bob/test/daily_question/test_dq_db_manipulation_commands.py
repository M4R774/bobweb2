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
    # # Daily Question Commands
    # #
    # def test_when_reply_to_message_with_command_overrides_it_as_daily_question(self):
    #     # Kun mihinkä vaan viestiin vastataan ja viesti sisältää komennon /kysymys tänään
    #     # Niin vanha päivänkysymys poistetaan ja replyn kohteena oleva viesti lisätään
    #     # sen päivän kysymykseksi
    #     raise NotImplementedError()
    #
    # def test_when_reply_to_message_with_command_overrides_prev_question_winner(self):
    #     # Sama kuin yllä, mutta edellisen päivän voittaja vaihdetaan
    #     raise NotImplementedError()
    #
    # def test_command_kysymys_tanaan_gives_season_summary(self):
    #     raise NotImplementedError()
    #
    # def test_command_kysymys_with_date_gives_that_date_summary(self):
    #     raise NotImplementedError()
    #
    # def test_command_with_invalid_date_gives_error(self):
    #     # Paramter is malformed or no question recorded on that day
    #     raise NotImplementedError()

import datetime
import os
from typing import List
from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import MagicMock

import django
from django.test import TestCase
from telegram import ReplyMarkup, User

from bobweb.bob import command_service
from bobweb.bob.test.daily_question.daily_question_test_utils import start_create_season_activity_get_host_message, \
    go_to_seasons_menu_get_host_message, populate_season_with_dq_and_answer
from bobweb.bob.utils_common import has_no
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion, DailyQuestionAnswer, TelegramUser, Chat
from bobweb.bob.command_daily_question import DailyQuestionCommand

from bobweb.bob.utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_to_contains, \
    assert_get_parameters_returns_expected_value, button_labels_from_reply_markup, MockMessage, MockUpdate, \
    get_latest_active_activity, assert_message_contains


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

    #
    # Daily Question Seasons
    #

    def test_kysymys_kommand_should_give_menu(self):
        update = MockUpdate().send_text("/kysymys")
        self.assertRegex(update.effective_message.reply_message_text, 'Valitse toiminto alapuolelta')

        reply_markup: ReplyMarkup = update.effective_message.reply_markup
        expected_buttons = ['Info', 'Kausi']
        actual_buttons = button_labels_from_reply_markup(reply_markup)
        # assertCountEqual tests that both iterable contains same items (misleading method name)
        self.assertCountEqual(expected_buttons, actual_buttons)

    def test_selecting_season_from_menu_shows_seasons_menu(self):
        host_message = go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text,
                         'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

    def test_season_menu_contains_active_season_info(self):
        populate_season_with_dq_and_answer(self)
        host_message = go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text, 'Aktiivisen kauden nimi: 1')

    def test_start_season_activity_creates_season(self):
        # 1. there is no season
        host_message = go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text,
                         'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

        # 2. season is created after create a season activity
        update = MockUpdate()
        host_message = start_create_season_activity_get_host_message(update)
        update.press_button('Tänään')
        update.send_text('1')
        self.assertRegex(host_message.reply_message_text, 'Uusi kausi aloitettu')

        # 3. Season has been created
        host_message = go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text, 'Aktiivisen kauden nimi: 1')

    def test_when_given_start_season_command_with_missing_info_gives_error(self):
        # Populate data, set end date to prepopulated season
        populate_season_with_dq_and_answer(self)
        season1 = DailyQuestionSeason.objects.get(id=1)
        season1.end_datetime = datetime.datetime(2022, 2, 2, 12, 00)
        season1.save()

        update = MockUpdate()
        host_message = start_create_season_activity_get_host_message(update)

        # test invalid start date inputs
        update.send_text('tiistai')
        self.assertRegex(host_message.reply_message_text, 'Antamasi päivämäärä ei ole tuettua muotoa')
        update.send_text('1.2.2022')
        self.assertRegex(host_message.reply_message_text, 'Uusi kausi voidaan merkitä alkamaan aikaisintaan edellisen '
                                                          'kauden päättymispäivänä')
        update.send_text('2.2.2022')
        self.assertRegex(host_message.reply_message_text, 'Valitse vielä kysymyskauden nimi')
        # test invalid season name inputs
        update.send_text('123456789 10 11 12 13 14')
        self.assertRegex(host_message.reply_message_text, 'Kysymyskauden nimi voi olla enintään 16 merkkiä pitkä')
        update.send_text('2')
        self.assertRegex(host_message.reply_message_text, 'Uusi kausi aloitettu')

    def test_end_season_activity_ends_season(self):
        populate_season_with_dq_and_answer(self)
        update = MockUpdate()
        update.effective_message.date = datetime.datetime(2022, 1, 5, 0, 0)
        host_message = go_to_seasons_menu_get_host_message(update)
        # should have active season
        self.assertRegex(host_message.reply_message_text, 'Aktiivisen kauden nimi: 1')

        update.press_button('Lopeta kausi')
        self.assertRegex(host_message.reply_message_text, r'Valitse ensin edellisen päivän kysymyksen \(02\.01\.2022\) '
                                                          r'voittaja alta')
        update.press_button('2')
        self.assertRegex(host_message.reply_message_text, r'Valitse kysymyskauden päättymispäivä alta')

        update.effective_message.reply_to_message = host_message  # Set update to be reply to host message

        # Test date input
        update.send_text('tiistai')
        self.assertRegex(host_message.reply_message_text, r'Antamasi päivämäärä ei ole tuettua muotoa')
        # Test that season can't end before last date of question
        update.send_text('1.1.2022')
        self.assertRegex(host_message.reply_message_text, r'Kysymyskausi voidaan merkitä päättyneeksi aikaisintaan '
                                                          r'viimeisen esitetyn päivän kysymyksen päivänä')
        update.send_text('31.01.2022')
        self.assertRegex(host_message.reply_message_text, r'Kysymyskausi merkitty päättyneeksi 31\.01\.2022')

        # Check that season has ended and the end date is correct
        update = MockUpdate()
        host_message = go_to_seasons_menu_get_host_message(update)
        assert_message_contains(self, host_message, ['Edellisen kauden nimi: 1', r'Kausi päättynyt: 31\.01\.2022'])

    def test_end_season_last_question_has_no_answers(self):
        populate_season_with_dq_and_answer(self)
        DailyQuestionAnswer.objects.filter(id=1).delete()  # Remove prepopulated answer

        update = MockUpdate()
        update.effective_message.date = datetime.datetime(2022, 1, 5, 0, 0)
        host_message = go_to_seasons_menu_get_host_message(update)
        # should have active season
        self.assertRegex(host_message.reply_message_text, 'Aktiivisen kauden nimi: 1')

        update.press_button('Lopeta kausi')
        assert_message_contains(self, host_message, ['Viimeiseen päivän kysymykseen ei ole lainkaan vastauksia',
                                                     'Haluatko varmasti päättää kauden?'])
        update.press_button('Kyllä, päätä kausi')
        assert_message_contains(self, host_message, ['Valitse kysymyskauden päättymispäivä alta'])

        update.effective_message.reply_to_message = host_message  # Set update to be reply to host message
        update.send_text('31.01.2022')
        self.assertRegex(host_message.reply_message_text, r'Kysymyskausi merkitty päättyneeksi 31\.01\.2022')

    def test_end_season_without_questions_season_is_deleted(self):
        populate_season_with_dq_and_answer(self)
        DailyQuestionAnswer.objects.filter(id=1).delete()  # Remove prepopulated answer
        DailyQuestion.objects.filter(id=1).delete()  # Remove prepopulated question

        update = MockUpdate()
        update.effective_message.date = datetime.datetime(2022, 1, 5, 0, 0)
        host_message = go_to_seasons_menu_get_host_message(update)

        # Ending season without questions deletes the season
        update.press_button('Lopeta kausi')
        assert_message_contains(self, host_message, ['Ei esitettyjä kysymyksiä kauden aikana, joten kausi '
                                                     'poistettu kokonaan.'])
        # Check that there is no season created for the chat
        host_message = go_to_seasons_menu_get_host_message(update)
        assert_message_contains(self, host_message,
                                ['Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille'])

    #
    # def test_when_given_end_season_command_gives_season_summary(self):
    #     raise NotImplementedError()
    #
    # #
    # # Daily Questions
    # #
    # def test_when_no_season_defined_should_ask_for_season_information(self):
    #     raise NotImplementedError()
    #
    # def test_when_given_season_creates_season_and_question(self):
    #     raise NotImplementedError()
    #
    # def test_when_chat_has_season_question_is_saved(self):
    #     raise NotImplementedError()
    #
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

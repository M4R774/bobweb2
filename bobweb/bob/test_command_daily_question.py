import datetime
import os
from typing import List
from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import MagicMock

import django
from django.test import TestCase
from telegram import ReplyMarkup, User

from bobweb.bob import command_service
from bobweb.bob.utils_common import has_no
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion, DailyQuestionAnswer, TelegramUser, Chat
from bobweb.bob.command_daily_question import DailyQuestionCommand

from bobweb.bob.utils_test import assert_has_reply_to, assert_no_reply_to, assert_reply_contains, \
    assert_get_parameters_returns_expected_value, button_labels_from_reply_markup, MockMessage, MockUpdate, \
    get_latest_active_activity


class DailyQuestionTestSuite(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuite, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    def setUp(self) -> None:
        # self.create_season_with_dq_and_answer()
        pass

    def populate_season_with_dq_and_answer(self):

        Chat.objects.create(id=1337, title="chat")
        self.chat = Chat.objects.get(id=1337)
        season_created = datetime.datetime(2022, 1, 1, 10, 5)
        DailyQuestionSeason.objects.create(id=1, chat=self.chat, season_name="1", start_datetime=season_created)
        self.season = DailyQuestionSeason.objects.get(id=1)
        TelegramUser.objects.create(id=1, username='1')
        self.user1 = TelegramUser.objects.get(id=1)
        TelegramUser.objects.create(id=2, username='2')
        self.user2 = TelegramUser.objects.get(id=2)
        DailyQuestion.objects.create(id=1,
                                     season=self.season,
                                     created_at=datetime.datetime(2022, 1, 1, 10, 10),
                                     date_of_question=datetime.datetime(2022, 1, 1, 0, 0),
                                     message_id=1,
                                     question_author=self.user1,
                                     content='dq1')
        self.dq = DailyQuestion.objects.get(id=1)
        DailyQuestionAnswer.objects.create(id=1,
                                           question=self.dq,
                                           created_at=datetime.datetime(2022, 1, 1, 11, 11),
                                           message_id=2,
                                           answer_author=self.user2,
                                           content="a1",
                                           is_winning_answer=True)
        self.dq_answer = DailyQuestionAnswer.objects.get(id=1)

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
    def go_to_seasons_menu_get_host_message(self, update: MockUpdate = None) -> MockMessage:
        if has_no(update):
            update = MockUpdate()
        update = update.send_text('/kysymys')  # Message from user
        update.press_button('Kausi')  # User presses button with label
        # Get the only activity's host message
        return get_latest_active_activity().host_message

    def start_create_season_activity_get_host_message(self, update: MockUpdate) -> MockMessage:
        update.send_text('/kysymys')  # Message from user
        update.press_button('Kausi')  # User presses button with label
        update.press_button('Aloita kausi')
        host_message = get_latest_active_activity().host_message
        update.effective_message.reply_to_message = host_message
        host_message.from_user = MagicMock(spec=User)
        return host_message

    def test_kysymys_kommand_should_give_menu(self):
        update = MockUpdate().send_text("/kysymys")
        self.assertRegex(update.effective_message.reply_message_text, 'Valitse toiminto alapuolelta')

        reply_markup: ReplyMarkup = update.effective_message.reply_markup
        expected_buttons = ['Info', 'Kausi']
        actual_buttons = button_labels_from_reply_markup(reply_markup)
        # assertCountEqual tests that both iterable contains same items (misleading method name)
        self.assertCountEqual(expected_buttons, actual_buttons)

    def test_selecting_season_from_menu_shows_seasons_menu(self):
        host_message = self.go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text,
                         'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

    def test_season_menu_contains_active_season_info(self):
        self.populate_season_with_dq_and_answer()
        host_message = self.go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text, 'Aktiivisen kauden nimi: 1')

    def test_start_season_activity_creates_season(self):
        # 1. there is no season
        host_message = self.go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text,
                         'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

        # 2. season is created after create a season activity
        update = MockUpdate()
        host_message = self.start_create_season_activity_get_host_message(update)
        update.press_button('Tänään')
        update.send_text('1')
        self.assertRegex(host_message.reply_message_text, 'Uusi kausi aloitettu')

        # 3. Season has been created
        host_message = self.go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text, 'Aktiivisen kauden nimi: 1')

    def test_when_given_start_season_command_with_missing_info_gives_error(self):
        # Populate data, set end date to prepopulated season
        self.populate_season_with_dq_and_answer()
        season1 = DailyQuestionSeason.objects.get(id=1)
        season1.end_datetime = datetime.datetime(2022, 2, 2, 12, 00)
        season1.save()

        update = MockUpdate()
        host_message = self.start_create_season_activity_get_host_message(update)

        # test invalid start date inputs
        update.send_text('tiistai')
        self.assertRegex(host_message.reply_message_text, 'Antamasi päivämäärä ei ole tuettua muotoa')
        update.send_text('1.2.2022')
        self.assertRegex(host_message.reply_message_text, 'Uusi kausi voidaan merkitä alkamaan aikaisintaan edellisen '
                                                          'kauden päättymispäivämääränä')
        update.send_text('2.2.2022')
        self.assertRegex(host_message.reply_message_text, 'Valitse vielä kysymyskauden nimi')
        # test invalid season name inputs
        update.send_text('123456789 10 11 12 13 14')
        self.assertRegex(host_message.reply_message_text, 'Kysymyskauden nimi voi olla enintään 16 merkkiä pitkä')
        update.send_text('2')
        self.assertRegex(host_message.reply_message_text, 'Uusi kausi aloitettu')

    # def test_when_new_season_overlaps_another_season_gives_error(self):
    #     raise NotImplementedError()
    #
    # def test_when_given_end_season_command_should_add_current_date_as_end(self):
    #     raise NotImplementedError()
    #
    # def test_when_given_end_season_command_with_date_adds_that_as_end(self):
    #     raise NotImplementedError()
    #
    # def test_when_given_end_season_command_gives_season_summary(self):
    #     raise NotImplementedError()
    #
    # def test_season_cant_be_ended_if_question_is_without_winner(self):
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

import datetime
import os
import django
from bobweb.bob import main  # needed to not cause circular import
from django.test import TestCase
from telegram import ReplyMarkup

from bobweb.bob.command_daily_question import DailyQuestionCommand
from bobweb.bob.test.daily_question.utils import start_create_season_activity_get_host_message, \
    go_to_seasons_menu_get_host_message, populate_season_with_dq_and_answer
from bobweb.bob.utils_test import button_labels_from_reply_markup, MockUpdate, \
    assert_message_contains, get_latest_active_activity, assert_has_reply_to, \
    assert_get_parameters_returns_expected_value
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion, DailyQuestionAnswer


class DailyQuestionTestSuite(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuite, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    def test_should_reply_to_question_commands_case_insenstivite_all_prefixes(self):
        assert_has_reply_to(self, "/kysymys")
        assert_has_reply_to(self, "!KYSymys")
        assert_has_reply_to(self, ".kysymys kausi")

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!kysymys', DailyQuestionCommand())

    def test_kysymys_kommand_should_give_menu(self):
        update = MockUpdate().send_text("/kysymys")
        self.assertRegex(update.effective_message.reply_message_text, 'Valitse toiminto alapuolelta')

        reply_markup: ReplyMarkup = update.effective_message.reply_markup
        expected_buttons = ['Info', 'Kausi']
        actual_buttons = button_labels_from_reply_markup(reply_markup)
        # assertCountEqual tests that both iterable contains same items (misleading method name)
        self.assertCountEqual(expected_buttons, actual_buttons)

    #
    # Daily Question Seasons - Menu
    #
    def test_selecting_season_from_menu_shows_seasons_menu(self):
        host_message = go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text,
                         'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

    def test_season_menu_contains_active_season_info(self):
        populate_season_with_dq_and_answer()
        host_message = go_to_seasons_menu_get_host_message()
        self.assertRegex(host_message.reply_message_text, 'Aktiivisen kauden nimi: 1')

    #
    # Daily Question Seasons - Start new season
    #
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
        populate_season_with_dq_and_answer()
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

    def test_when_dq_triggered_without_season_should_start_activity_and_save_dq(self):
        MockUpdate().send_text("#päivänkysymys kuka?")
        host_message = get_latest_active_activity().host_message
        assert_message_contains(self, host_message, ['Ryhmässä ei ole aktiivista kautta päivän kysymyksille',
                                                     'Valitse ensin kysymyskauden aloituspäivämäärä'])
        update = MockUpdate()
        update.effective_message.reply_to_message = host_message  # Set update to be reply to host message
        update.send_text('2022-02-01')
        update.send_text('season name')
        assert_message_contains(self, host_message, ['Uusi kausi aloitettu ja aiemmin lähetetty päivän kysymys '
                                                     'tallennettu linkitettynä juuri luotuun kauteen'])
        seasons = list(DailyQuestionSeason.objects.all())
        self.assertEqual(1, len(seasons))
        self.assertEqual('season name', seasons[0].season_name)

        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)

    #
    # Daily Question Seasons - End season
    #
    def test_end_season_activity_ends_season(self):
        populate_season_with_dq_and_answer()
        # Check that user's '2' answer is not marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=2))
        self.assertFalse(answers[0].is_winning_answer)

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

        # Check that user's '2' reply to the daily question has been marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=2))
        self.assertTrue(answers[0].is_winning_answer)

    def test_end_season_last_question_has_no_answers(self):
        populate_season_with_dq_and_answer()
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
        populate_season_with_dq_and_answer()
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

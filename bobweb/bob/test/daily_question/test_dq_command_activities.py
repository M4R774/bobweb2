import datetime
import os
import django
import pytz
from freezegun import freeze_time

from bobweb.bob import main  # needed to not cause circular import
from django.test import TestCase

from bobweb.bob.activities.daily_question.end_season_states import end_season_no_answers_for_last_dq, end_date_msg, \
    no_dq_season_deleted_msg
from bobweb.bob.activities.daily_question.start_season_states import get_message_body, get_season_created_msg
from bobweb.bob.command_daily_question import DailyQuestionCommand
from bobweb.bob.test.daily_question.utils import go_to_seasons_menu_v2, \
    populate_season_with_dq_and_answer_v2, populate_season_v2
from bobweb.bob.tests_mocks_v2 import MockChat, init_chat_user
from bobweb.bob.tests_utils import assert_has_reply_to, assert_get_parameters_returns_expected_value
from bobweb.bob.tests_msg_btn_utils import button_labels_from_reply_markup
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion, DailyQuestionAnswer


@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
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

    #
    # Daily Question Seasons - Menu
    #

    def test_kysymys_kommand_should_give_menu(self):
        chat, user = init_chat_user()
        user.send_update("/kysymys")
        self.assertRegex(chat.bot.messages[-1].text, 'Valitse toiminto alapuolelta')

        expected_buttons = ['Info ⁉', 'Kausi 📅', 'Tilastot 📊']
        actual_buttons = button_labels_from_reply_markup(chat.bot.messages[-1].reply_markup)
        # assertCountEqual tests that both iterable contains same items (misleading method name)
        self.assertCountEqual(expected_buttons, actual_buttons)

    def test_selecting_season_from_menu_shows_seasons_menu(self):
        chat, user = init_chat_user()
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_msg(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

    def test_season_menu_contains_active_season_info(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_msg(), 'Aktiivisen kauden nimi: season_name')

    #
    # Daily Question Seasons - Start new season
    #

    def test_start_season_activity_creates_season(self):
        # 1. there is no season
        chat, user = init_chat_user()
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_msg(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

        # 2. season is created after create a season activity
        go_to_seasons_menu_v2(user)
        user.press_button('Aloita kausi')
        user.press_button('Tänään')
        user.reply_to_bot('[season name]')

        self.assertRegex(chat.last_bot_msg(), 'Uusi kausi aloitettu')

        # 3. Season has been created
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_msg(), r'Aktiivisen kauden nimi: \[season name\]')

    def test_when_given_start_season_command_with_missing_info_gives_error(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        season = DailyQuestionSeason.objects.first()
        season.end_datetime = datetime.datetime(2022, 10, 10, 00, tzinfo=pytz.UTC)
        season.save()

        go_to_seasons_menu_v2(user)
        user.press_button('Aloita kausi')

        user.reply_to_bot('tiistai')
        self.assertRegex(chat.last_bot_msg(), 'Antamasi päivämäärä ei ole tuettua muotoa')
        user.reply_to_bot('1.1.2000')
        self.assertRegex(chat.last_bot_msg(), 'Uusi kausi voidaan merkitä alkamaan aikaisintaan edellisen '
                                              'kauden päättymispäivänä')
        user.reply_to_bot('2.1.2023')
        self.assertRegex(chat.last_bot_msg(), 'Valitse vielä kysymyskauden nimi')
        # test invalid season name inputs
        user.reply_to_bot('123456789 10 11 12 13 14')
        self.assertRegex(chat.last_bot_msg(), 'Kysymyskauden nimi voi olla enintään 16 merkkiä pitkä')
        user.reply_to_bot('2')
        self.assertRegex(chat.last_bot_msg(), 'Uusi kausi aloitettu')

    def test_when_dq_triggered_without_season_should_start_activity_and_save_dq(self):
        chat, user = init_chat_user()
        user.send_update('#päivänkysymys kuka?')
        self.assertRegex(chat.last_bot_msg(), get_message_body(True))

        user.reply_to_bot('2022-02-01')
        user.reply_to_bot('[season name]')
        self.assertRegex(chat.last_bot_msg(), get_season_created_msg(True))

        seasons = list(DailyQuestionSeason.objects.all())
        self.assertEqual(1, len(seasons))
        self.assertEqual('[season name]', seasons[0].season_name)

        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)

    #
    # Daily Question Seasons - End season
    #

    def test_end_season_activity_ends_season(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)
        user = chat.users[-1]
        # Check that no answer is marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertFalse(answers[0].is_winning_answer)

        go_to_seasons_menu_v2(user)
        # should have active season
        self.assertRegex(chat.last_bot_msg(), 'Aktiivisen kauden nimi: season_name')

        user.press_button('Lopeta kausi')
        self.assertRegex(chat.last_bot_msg(), r'Valitse ensin edellisen päivän kysymyksen \(02\.01\.2023\) '
                                              r'voittaja alta')
        user.press_button('c')  # MockUser username
        self.assertRegex(chat.last_bot_msg(), r'Valitse kysymyskauden päättymispäivä alta')

        # Test date input
        user.reply_to_bot('tiistai')
        self.assertRegex(chat.last_bot_msg(), r'Antamasi päivämäärä ei ole tuettua muotoa')
        # Test that season can't end before last date of question
        user.reply_to_bot('1.1.2000')
        self.assertRegex(chat.last_bot_msg(), r'Kysymyskausi voidaan merkitä päättyneeksi aikaisintaan '
                                              'viimeisen esitetyn päivän kysymyksen päivänä')
        user.reply_to_bot('31.01.2023')
        self.assertRegex(chat.last_bot_msg(), r'Kysymyskausi merkitty päättyneeksi 31\.01\.2023')

        # Check that season has ended and the end date is correct
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_msg(), r'Kausi päättynyt: 31\.01\.2023')

        # Check that user's '2' reply to the daily question has been marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertTrue(answers[0].is_winning_answer)

    def test_end_season_last_question_has_no_answers(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        DailyQuestionAnswer.objects.filter().delete()  # Remove prepopulated answer

        # should have active season
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_msg(), 'Aktiivisen kauden nimi: season_name')

        user.press_button('Lopeta kausi')
        self.assertRegex(chat.last_bot_msg(), end_season_no_answers_for_last_dq)
        user.press_button('Kyllä, päätä kausi')
        self.assertRegex(chat.last_bot_msg(), end_date_msg)

        user.reply_to_bot('31.01.2023')
        self.assertRegex(chat.last_bot_msg(), r'Kysymyskausi merkitty päättyneeksi 31\.01\.2023')

    def test_end_season_without_questions_season_is_deleted(self):
        chat, user = init_chat_user()
        populate_season_v2(chat)

        # Ending season without questions deletes the season
        go_to_seasons_menu_v2(user)
        user.press_button('Lopeta kausi')
        self.assertRegex(chat.last_bot_msg(), no_dq_season_deleted_msg)

        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_msg(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

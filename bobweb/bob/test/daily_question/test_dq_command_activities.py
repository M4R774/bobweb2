import datetime
import os
from unittest.mock import Mock

from django.core import management

from bobweb.bob import main

import django
import pytz
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from openpyxl import Workbook
from openpyxl.reader.excel import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from telegram.ext import CallbackContext

from bobweb.bob import main  # needed to not cause circular import
from django.test import TestCase

from bobweb.bob.activities.daily_question.daily_question_menu_states import get_xlsx_btn, \
    end_season_btn, stats_btn, info_btn, season_btn, main_menu_basic_info, start_season_btn
from bobweb.bob.activities.daily_question.dq_excel_exporter_v2 import HEADING_HEIGHT, ColumnHeaders, INFO_WIDTH
from bobweb.bob.activities.daily_question.end_season_states import end_season_no_answers_for_last_dq, end_date_msg, \
    no_dq_season_deleted_msg, end_season_cancelled, end_anyway_btn
from bobweb.bob.activities.daily_question.start_season_states import get_message_body, get_season_created_msg, \
    start_season_cancelled
from bobweb.bob.command_daily_question import DailyQuestionCommand
from bobweb.bob.test.daily_question.utils import go_to_seasons_menu_v2, \
    populate_season_with_dq_and_answer_v2, populate_season_v2, kysymys_command, go_to_stats_menu_v2
from bobweb.bob.tests_mocks_v2 import MockChat, init_chat_user, MockUser
from bobweb.bob.tests_utils import assert_command_triggers
from bobweb.bob.tests_msg_btn_utils import button_labels_from_reply_markup
from bobweb.bob.utils_common import fitzstr_from
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion, DailyQuestionAnswer
from bobweb.bob.activities.activity_state import back_button, cancel_button


@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
class DailyQuestionTestSuiteV2(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuiteV2, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/kysymys', '!kysymys', '.kysymys', '/KYSYMYS']
        should_not_trigger = ['kysymys', 'test /kysymys', '/kysymys test']
        await assert_command_triggers(self, DailyQuestionCommand, should_trigger, should_not_trigger)

    #
    # Daily Question Seasons - Menu
    #

    async def test_kysymys_kommand_should_give_menu(self):
        chat, user = init_chat_user()
        await user.send_message(kysymys_command)
        self.assertRegex(chat.bot.messages[-1].text, 'Valitse toiminto alapuolelta')

        expected_buttons = ['Info ⁉', 'Kausi 📅', 'Tilastot 📊']
        actual_buttons = button_labels_from_reply_markup(chat.bot.messages[-1].reply_markup)
        # assertCountEqual tests that both iterable contains same items (misleading method name)
        self.assertCountEqual(expected_buttons, actual_buttons)

    async def test_selecting_season_from_menu_shows_seasons_menu(self):
        chat, user = init_chat_user()
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_txt(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

    async def test_season_menu_contains_active_season_info(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_txt(), 'Aktiivisen kauden nimi: season_name')

    #
    # Daily Question Seasons - Start new season
    #

    async def test_start_season_activity_creates_season(self):
        # 1. there is no season
        chat, user = init_chat_user()
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_txt(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

        # 2. season is created after create a season activity
        go_to_seasons_menu_v2(user)
        await user.press_button(start_season_btn)
        await user.press_button_with_text('Tänään')
        await user.reply_to_bot('[season name]')

        self.assertRegex(chat.last_bot_txt(), 'Uusi kausi aloitettu')

        # 3. Season has been created
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_txt(), r'Aktiivisen kauden nimi: \[season name\]')

    async def test_when_given_start_season_command_with_missing_info_gives_error(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        season = DailyQuestionSeason.objects.first()
        season.end_datetime = datetime.datetime(2022, 10, 10, 00, tzinfo=pytz.UTC)
        season.save()

        go_to_seasons_menu_v2(user)
        await user.press_button(start_season_btn)

        await user.reply_to_bot('tiistai')
        self.assertRegex(chat.last_bot_txt(), 'Antamasi päivämäärä ei ole tuettua muotoa')
        await user.reply_to_bot('1.1.2000')
        self.assertRegex(chat.last_bot_txt(), 'Uusi kausi voidaan merkitä alkamaan aikaisintaan edellisen '
                                              'kauden päättymispäivänä')
        await user.reply_to_bot('2.1.2023')
        self.assertRegex(chat.last_bot_txt(), 'Valitse vielä kysymyskauden nimi')
        # test invalid season name inputs
        await user.reply_to_bot('123456789 10 11 12 13 14')
        self.assertRegex(chat.last_bot_txt(), 'Kysymyskauden nimi voi olla enintään 16 merkkiä pitkä')
        await user.reply_to_bot('2')
        self.assertRegex(chat.last_bot_txt(), 'Uusi kausi aloitettu')

    async def test_when_dq_triggered_without_season_should_start_activity_and_save_dq(self):
        chat, user = init_chat_user()
        await user.send_message('#päivänkysymys kuka?')
        self.assertRegex(chat.last_bot_txt(), get_message_body(True))

        await user.reply_to_bot('2022-02-01')
        await user.reply_to_bot('[season name]')
        self.assertRegex(chat.last_bot_txt(), get_season_created_msg(True))

        seasons = list(DailyQuestionSeason.objects.all())
        self.assertEqual(1, len(seasons))
        self.assertEqual('[season name]', seasons[0].season_name)

        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)

    #
    # Daily Question Seasons - End season
    #

    async def test_end_season_activity_ends_season(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)
        user = chat.users[-1]
        # Check that no answer is marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertFalse(answers[0].is_winning_answer)

        go_to_seasons_menu_v2(user)
        # should have active season
        self.assertRegex(chat.last_bot_txt(), 'Aktiivisen kauden nimi: season_name')

        await user.press_button(end_season_btn)
        self.assertRegex(chat.last_bot_txt(), r'Valitse ensin edellisen päivän kysymyksen \(02\.01\.2023\) '
                                              r'voittaja alta')
        await user.press_button_with_text(user.username)  # MockUser username
        self.assertRegex(chat.last_bot_txt(), r'Valitse kysymyskauden päättymispäivä alta')

        # Test date input
        await user.reply_to_bot('tiistai')
        self.assertRegex(chat.last_bot_txt(), r'Antamasi päivämäärä ei ole tuettua muotoa')
        # Test that season can't end before last date of question
        await user.reply_to_bot('1.1.2000')
        self.assertRegex(chat.last_bot_txt(), r'Kysymyskausi voidaan merkitä päättyneeksi aikaisintaan '
                                              'viimeisen esitetyn päivän kysymyksen päivänä')
        await user.reply_to_bot('31.01.2023')
        self.assertRegex(chat.last_bot_txt(), r'Kysymyskausi merkitty päättyneeksi 31\.01\.2023')

        # Check that season has ended and the end date is correct
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_txt(), r'Kausi päättynyt: 31\.01\.2023')

        # Check that user's '2' reply to the daily question has been marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertTrue(answers[0].is_winning_answer)

    async def test_end_season_last_question_has_no_answers(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        DailyQuestionAnswer.objects.filter().delete()  # Remove prepopulated answer

        # should have active season
        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_txt(), 'Aktiivisen kauden nimi: season_name')

        await user.press_button(end_season_btn)
        self.assertRegex(chat.last_bot_txt(), end_season_no_answers_for_last_dq)
        await user.press_button(end_anyway_btn)
        self.assertRegex(chat.last_bot_txt(), end_date_msg)

        await user.reply_to_bot('31.01.2023')
        self.assertRegex(chat.last_bot_txt(), r'Kysymyskausi merkitty päättyneeksi 31\.01\.2023')

    async def test_end_season_without_questions_season_is_deleted(self):
        chat, user = init_chat_user()
        populate_season_v2(chat)

        # Ending season without questions deletes the season
        go_to_seasons_menu_v2(user)
        await user.press_button(end_season_btn)
        self.assertRegex(chat.last_bot_txt(), no_dq_season_deleted_msg)

        go_to_seasons_menu_v2(user)
        self.assertRegex(chat.last_bot_txt(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

    #
    # Daily Question menu - Stats
    #

    @freeze_time('2023-01-02', as_kwarg='clock')
    async def test_stats_should_show_season_status(self, clock: FrozenDateTimeFactory):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)

        # As prepopulated user who has asked one question, check that their stats are shown
        # However, first question of the season is not included in the stats
        user1 = chat.users[-1]
        user2 = MockUser(chat=chat)

        go_to_stats_menu_v2(user1)
        self.assertIn('Kysymyksiä esitetty: 1', chat.last_bot_txt())
        self.assertIn(f'{user1.username}   |  0|  1', chat.last_bot_txt())

        # After single daily question, should be updated to 1 victory
        clock.tick(datetime.timedelta(days=1))
        dq_msg = await user1.send_message('#päivänkysymys')

        go_to_stats_menu_v2(user1)
        self.assertIn('Kysymyksiä esitetty: 2', chat.last_bot_txt())
        self.assertIn(f'{user1.username}   |  1|  1', chat.last_bot_txt())

        # Now simulate situation, where questions are bounced between 2 users
        clock.tick(datetime.timedelta(days=1))

        await user2.send_message('vastaus', reply_to_message=dq_msg)
        dq_msg = await user2.send_message('#päivänkysymys')
        clock.tick(datetime.timedelta(days=1))
        await user1.send_message('vastaus', reply_to_message=dq_msg)
        await user1.send_message('#päivänkysymys')

        go_to_stats_menu_v2(user1)
        self.assertIn('Kysymyksiä esitetty: 4', chat.last_bot_txt())
        self.assertIn(f'{user1.username}   |  2|  2', chat.last_bot_txt())
        self.assertIn(f'{user2.username}   |  1|  1', chat.last_bot_txt())

    @freeze_time('2023-01-02', as_kwarg='clock')
    async def test_stats_should_be_calculated_based_on_presented_daily_questions(self, clock: FrozenDateTimeFactory):
        chat = MockChat()
        populate_season_v2(chat)

        # Define 2 users and add the two to a list
        users = [chat.users[-1], MockUser(chat=chat)]
        # Do n iterations where users ask daily questions turn by turn
        for i in range(0, 6):
            user = users[i % 2]  # get either first or second user based on reminder on modulus check
            await user.send_message(f'#päivänkysymys {i + 1}')
            clock.tick(datetime.timedelta(days=1))

        # Now each user has asked 3 questions and answered 0 questions. However, first question of the season is
        # not included in the score, so users[0] should have score of 2 and users[1] should have score of 3
        # Now stats page is expected to have score of 3 for each
        go_to_stats_menu_v2(users[0])
        self.assertIn('Kysymyksiä esitetty: 6', chat.last_bot_txt())
        self.assertIn(f'{users[1].username}   |  3|  0', chat.last_bot_txt())
        self.assertIn(f'{users[0].username}   |  2|  0', chat.last_bot_txt())

    #
    # Daily Question menu - Stats - Exel exporter
    #

    async def test_exported_stats_excel(self):
        chat = MockChat()
        season = populate_season_with_dq_and_answer_v2(chat)
        user = chat.users[-1]

        # Download excel. With ChatMockV2, document binary stream is saved to the chat objects document list
        # As CallbackContext.bot is not used in Mock v2 classes, mock is used
        go_to_stats_menu_v2(user)
        context = Mock(spec=CallbackContext)
        context.bot = chat.bot
        await user.press_button(get_xlsx_btn, context=context)

        excel_binary = chat.media_and_documents[-1]
        wb: Workbook = load_workbook(filename=excel_binary)
        ws: Worksheet = wb.active

        # Get list of values for each row
        rows = [[col.value for col in row] for row in ws.rows if row is not None]
        # assertCountEqual tests that both iterable contains same items (misleading method name)
        expected_dq_headers = [header[1].value for header in enumerate(ColumnHeaders)]
        self.assertSequenceEqual(expected_dq_headers, rows[HEADING_HEIGHT][:INFO_WIDTH])

        dq: DailyQuestion = DailyQuestion.objects.first()

        row = rows[HEADING_HEIGHT + 1]
        # Order nubmer of daily question in season
        self.assertEqual(1, row[0])
        # Daily question created at
        self.assertEqual(fitzstr_from(dq.created_at), fitzstr_from(row[1]))
        # Daily Question date of the question
        self.assertEqual(fitzstr_from(dq.date_of_question), fitzstr_from(row[2]))
        # Link to the question message
        self.assertEqual(f'https://t.me/c/{season.chat_id}/{dq.message_id}', row[3])
        # Username of the question author
        self.assertEqual(dq.question_author.username, row[4])
        # Daily question message content
        self.assertEqual('dq1', row[5])
        # Number of answers
        self.assertEqual(1, row[6])
        self.assertEqual(None, row[7])
        self.assertEqual(None, row[8])

        dq_answer: DailyQuestionAnswer = DailyQuestionAnswer.objects.first()
        # Answer content
        self.assertEqual(dq_answer.content, row[9])
        # Accuracy
        self.assertEqual(None, row[10])
        # Order number of answer
        self.assertEqual(1, row[11])

    #
    # Daily Question menu - Navigation
    #

    async def test_menu_back_buttons_no_season(self):
        chat, user = init_chat_user()
        expected_str = [main_menu_basic_info,
                        'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille',
                        'Ei lainkaan kysymyskausia.']
        await self.navigate_all_menus_from_main_menu(chat, user, expected_str)

    async def test_menu_back_buttons_has_season(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        expected_str = [main_menu_basic_info,
                        'Aktiivisen kauden nimi:',
                        'Päivän kysyjät 🧐']
        await self.navigate_all_menus_from_main_menu(chat, user, expected_str)

    async def navigate_all_menus_from_main_menu(self, chat, user, expected_str):
        await user.send_message(kysymys_command, chat)
        # Visit all 3 menu states and return to main menu

        user.press_button(info_btn)
        self.assertIn(expected_str[0], chat.last_bot_txt())
        user.press_button(back_button)
        self.assertIn('Valitse toiminto alapuolelta', chat.last_bot_txt())

        user.press_button(season_btn)
        self.assertIn(expected_str[1], chat.last_bot_txt())
        user.press_button(back_button)
        self.assertIn('Valitse toiminto alapuolelta', chat.last_bot_txt())

        user.press_button(stats_btn)
        self.assertIn(expected_str[2], chat.last_bot_txt())
        user.press_button(back_button)
        self.assertIn('Valitse toiminto alapuolelta', chat.last_bot_txt())

    async def test_cancel_season_start_and_cancel_season_end_buttons(self):
        # First test that user can cancel starting a season
        chat, user = init_chat_user()
        go_to_seasons_menu_v2(user)
        await user.press_button(start_season_btn)
        await user.press_button(cancel_button)

        self.assertIn(start_season_cancelled, chat.last_bot_txt())
        seasons = DailyQuestionSeason.objects.all()
        self.assertSequenceEqual([], list(seasons))

        # Then test that user can cancel ending a season
        populate_season_with_dq_and_answer_v2(chat)

        go_to_seasons_menu_v2(user)
        await user.press_button(end_season_btn)
        await user.press_button(cancel_button)

        self.assertIn(end_season_cancelled, chat.last_bot_txt())
        season = DailyQuestionSeason.objects.first()
        self.assertIsNone(season.end_datetime)

    #
    # Daily Question menu - Misc / Other
    #

    async def test_when_next_day_dq_has_been_asked_end_season_gives_its_date_as_button(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)
        user = chat.users[-1]

        # User sends new daily question. As today already has one, it is set to be next days question
        await user.send_message('#päivänkysymys dato_of_question should be next day')
        last_dq = DailyQuestion.objects.last()
        self.assertIn('2023-01-03', str(last_dq.date_of_question))

        # Now it user wants to end season, it cannot be ended before the date of latest dq
        go_to_seasons_menu_v2(user)
        await user.press_button(end_season_btn)
        await user.press_button(end_anyway_btn)

        # Test that bot gives button with next days date as it's the last date with daily question
        expected_buttons = ['Peruuta ❌', 'ma 03.01.2023']
        actual_buttons = button_labels_from_reply_markup(chat.bot.messages[-1].reply_markup)
        self.assertSequenceEqual(expected_buttons, actual_buttons)

        # Try to make season end today. Should give error
        await user.reply_to_bot('02.01.2023')
        expected_reply = 'Kysymyskausi voidaan merkitä päättyneeksi aikaisintaan viimeisen esitetyn päivän kysymyksen päivänä'
        self.assertIn(expected_reply, chat.last_bot_txt())
        await user.press_button_with_text('ma 03.01.2023')
        self.assertIn('Kysymyskausi merkitty päättyneeksi 03.01.2023', chat.last_bot_txt())
        self.assertIn('2023-01-03', str(DailyQuestionSeason.objects.first().end_datetime))




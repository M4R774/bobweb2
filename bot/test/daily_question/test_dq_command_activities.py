import datetime
from unittest.mock import Mock

import pytest
from django.core import management

import django
import pytz
from django.db.models import QuerySet
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from openpyxl import Workbook
from openpyxl.reader.excel import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from telegram.ext import CallbackContext

from bot import main, database  # needed to not cause circular import
from django.test import TestCase

from bot.activities.daily_question import daily_question_menu_states
from bot.activities.daily_question.daily_question_menu_states import get_xlsx_btn, \
    end_season_btn, stats_btn, info_btn, main_menu_basic_info, start_season_btn, DQMainMenuState, \
    get_message_body, get_season_created_msg, end_date_msg, no_dq_season_deleted_msg, end_season_cancelled, \
    SetLastQuestionWinnerState
from bot.activities.daily_question.dq_excel_exporter_v2 import HEADING_HEIGHT, ColumnHeaders, INFO_WIDTH
from bot.commands.daily_question import DailyQuestionCommand
from bot.message_board import MessageBoardMessage
from bot.test.daily_question.utils import go_to_main_menu, \
    populate_season_with_dq_and_answer_v2, populate_season_v2, kysymys_command, go_to_stats_menu
from bot.tests_mocks_v2 import MockChat, init_chat_user, MockUser, assert_buttons_contain, assert_buttons_equals
from bot.tests_utils import assert_command_triggers
from bot.utils_common import fitzstr_from
from web.bobapp.models import DailyQuestionSeason, DailyQuestion, DailyQuestionAnswer
from bot.activities.activity_state import back_button, cancel_button


@pytest.mark.asyncio
@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
class DailyQuestionTestSuiteV2(django.test.TransactionTestCase):
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

    async def test_question_command_should_give_main_menu_when_no_daily_question_seasons(self):
        chat, user = init_chat_user()
        await user.send_message(kysymys_command)

        self.assertIn(DQMainMenuState._no_seasons_text, chat.last_bot_txt())
        assert_buttons_equals(self, ['Info ⁉', 'Aloita kausi 🚀', 'Tilastot 📊'], chat.last_bot_msg())

    async def test_question_command_should_give_stats_menu_when_has_seasons(self):
        chat, user = init_chat_user()
        await populate_season_with_dq_and_answer_v2(chat)

        await user.send_message(kysymys_command)
        self.assertIn('Kausi: season_name', chat.last_bot_txt())
        assert_buttons_contain(self, chat.last_bot_msg(), [back_button.text, '[1]: season_name'])

    async def test_selecting_season_from_menu_shows_seasons_menu(self):
        chat, user = init_chat_user()
        await go_to_main_menu(user)
        self.assertRegex(chat.last_bot_txt(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

    #
    # Daily Question Seasons - Start new season
    #
    async def test_start_season_activity_creates_season(self):
        # 1. there is no season
        chat, user = init_chat_user()
        await go_to_main_menu(user)
        self.assertRegex(chat.last_bot_txt(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

        # 2. season is created after create a season activity
        await go_to_main_menu(user)
        await user.press_button(start_season_btn)

        # Get today button from the last message
        await user.press_button_with_text('Tänään (02.01.2023)')
        await user.reply_to_bot('[season name]')

        self.assertRegex(chat.last_bot_txt(), 'Uusi kausi aloitettu')

        # 3. Season has been created
        await go_to_main_menu(user)
        assert_buttons_contain(self, chat.last_bot_msg(), ['Lopeta kausi 🏁'])

    async def test_when_given_start_season_command_with_missing_info_gives_error(self):
        chat, user = init_chat_user()
        await populate_season_with_dq_and_answer_v2(chat)
        season = DailyQuestionSeason.objects.first()
        season.end_datetime = datetime.datetime(2022, 10, 10, 00, tzinfo=pytz.UTC)
        season.save()

        await go_to_main_menu(user)
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
        await populate_season_with_dq_and_answer_v2(chat)
        user = chat.users[-1]
        # Check that no answer is marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertFalse(answers[0].is_winning_answer)

        await go_to_main_menu(user)
        await user.press_button(end_season_btn)
        self.assertIn('Valitse ensin edellisen päivän kysymyksen (02.01.2023) voittaja alta.', chat.last_bot_txt())
        await user.press_button_with_text(user.username)  # MockUser username
        self.assertIn(f'Viimeisen kysymyksen voittajaksi valittu {user.username}.\nValitse kysymyskauden '
                      f'päättymispäivä alta tai anna se vastaamalla tähän viestiin.', chat.last_bot_txt())

        # Test date input
        await user.reply_to_bot('tiistai')
        self.assertIn('Antamasi päivämäärä ei ole tuettua muotoa', chat.last_bot_txt())
        # Test that season can't end before last date of question
        await user.reply_to_bot('1.1.2000')
        self.assertIn('Kysymyskausi voidaan merkitä päättyneeksi aikaisintaan '
                      'viimeisen esitetyn päivän kysymyksen päivänä', chat.last_bot_txt())
        await user.reply_to_bot('31.01.2023')
        self.assertIn('Kysymyskausi merkitty päättyneeksi 31.01.2023', chat.last_bot_txt())

        # Check that season has ended and the end date is correct
        season = list(DailyQuestionSeason.objects.filter(chat__id=chat.id))[-1]
        self.assertEqual(datetime.datetime(2023, 1, 31, tzinfo=datetime.timezone.utc), season.end_datetime)
        # Check that user's '2' reply to the daily question has been marked as winning one
        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertTrue(answers[0].is_winning_answer)

    async def test_end_season_user_list_pagination(self):
        """ Test that when season is ended and winner for the last question is set, the pagination of choosing
            the last question winner works as expected. Should change page and the buttons should update accordingly """
        chat, user = init_chat_user()
        await populate_season_with_dq_and_answer_v2(chat)

        # Set users per page to be 3 while testing
        SetLastQuestionWinnerState._users_per_page = 3
        # Note, population creates 4 users to the chat. Add 3 more so there are 3 pages

        for i in range(3):
            new_user = MockUser(first_name=f'user_{i + 1}')
            await new_user.send_message(f'hi from user {new_user.name}', chat=chat)

        await go_to_main_menu(user)
        await user.press_button(end_season_btn)

        # Check for strict equality for the first row.
        self.assertIn('Näytetään sivu 1/3.', chat.last_bot_txt())
        first_button_row = chat.last_bot_msg().reply_markup.inline_keyboard[0]
        self.assertEqual(['Peruuta ❌', 'Seuraava sivu'],
                         [button.text for button in first_button_row])

        await user.press_button_with_text('Seuraava sivu')

        # Now should show that page 2 out of 3 is shown
        self.assertIn('Näytetään sivu 2/3.', chat.last_bot_txt())
        first_button_row = chat.last_bot_msg().reply_markup.inline_keyboard[0]
        self.assertEqual(['Peruuta ❌', 'Edellinen sivu', 'Seuraava sivu'],
                         [button.text for button in first_button_row])

        # Contains 1 user created by populator function and 2 users created by the loop
        assert_buttons_contain(self, chat.last_bot_msg(),
                               ['user_1', 'user_2',])

        await user.press_button_with_text('Seuraava sivu')

        self.assertIn('Näytetään sivu 3/3.', chat.last_bot_txt())
        assert_buttons_equals(self, ['Peruuta ❌', 'Edellinen sivu', 'user_3'], chat.last_bot_msg())

        # And as a last test, pressing previous page button should change to the previous page
        await user.press_button_with_text('Edellinen sivu')
        self.assertIn('Näytetään sivu 2/3.', chat.last_bot_txt())
        assert_buttons_contain(self, chat.last_bot_msg(),
                               ['user_1', 'user_2',])

    async def test_end_season_if_last_question_winner_has_answer_it_is_set_as_winning(self):
        """ Tests that when ending the season and choosing a user as a winner that has saved answer for the last
            question, that question is updated to be the winning answer and no new answer is added. """
        chat, user = init_chat_user()
        await populate_season_with_dq_and_answer_v2(chat)

        # Find the only answer
        answer_author = chat.users[-1]
        answer_message = answer_author.messages[-1]

        answer: DailyQuestionAnswer = DailyQuestionAnswer.objects.all()[0]
        self.assertEqual(False, answer.is_winning_answer)
        self.assertEqual(answer_message.text, answer.content)

        # End the season
        await go_to_main_menu(user)
        await user.press_button(end_season_btn)

        # Select user as the winner -> should state that the user has been selected as the winner
        self.assertIn('Valitse ensin edellisen päivän kysymyksen (02.01.2023) voittaja alta.', chat.last_bot_txt())
        await user.press_button_with_text(answer_author.username)
        self.assertIn(f'Viimeisen kysymyksen voittajaksi valittu {answer_author.username}.', chat.last_bot_txt())
        await user.press_button_with_text('ma 02.01.2023')
        self.assertIn('Kysymyskausi merkitty päättyneeksi tänään.', chat.last_bot_txt())

        # Now as the last thing, check that there is still only one answer and that it has been set as winning answer
        all_answers = DailyQuestionAnswer.objects.all()
        self.assertEqual(1, len(all_answers))
        self.assertEqual(True, all_answers[0].is_winning_answer)

    async def test_end_season_if_last_question_winner_has_no_answer_new_is_created(self):
        """ Tests that if selected winner of the last question has no answer saved for that question, a new answer is
            saved that only contains reference to the question, to the user and it is a winning answer. """
        chat, user = init_chat_user()
        await populate_season_with_dq_and_answer_v2(chat)

        # End the season. The first user in the chat is chosen as the winning user and they have no answers saved
        user_to_set_as_winner = chat.users[0]
        winning_answers: QuerySet = DailyQuestionAnswer.objects.filter(answer_author__id=user_to_set_as_winner.id)
        self.assertEqual(0, len(winning_answers))

        winning_answers: QuerySet = DailyQuestionAnswer.objects.filter(is_winning_answer=True)
        self.assertEqual(0, len(winning_answers))

        await go_to_main_menu(user)
        await user.press_button(end_season_btn)
        await user.press_button_with_text(user_to_set_as_winner.username)
        self.assertIn(f'Viimeisen kysymyksen voittajaksi valittu {user_to_set_as_winner.username}.',
                      chat.last_bot_txt())
        await user.press_button_with_text('ma 02.01.2023')
        self.assertIn('Kysymyskausi merkitty päättyneeksi tänään.', chat.last_bot_txt())

        # Now should have 1 winning answer
        user_to_set_as_winner = chat.users[0]
        winning_answers: QuerySet = DailyQuestionAnswer.objects.filter(answer_author__id=user_to_set_as_winner.id)
        self.assertEqual(1, len(winning_answers))

        winning_answers: QuerySet = DailyQuestionAnswer.objects.filter(is_winning_answer=True)
        self.assertEqual(1, len(winning_answers))

        winning_answer: DailyQuestionAnswer = winning_answers[0]
        self.assertEqual(True, winning_answer.is_winning_answer)
        self.assertEqual(user_to_set_as_winner.id, winning_answer.answer_author.id)
        self.assertIsNotNone(winning_answer.question)
        self.assertIsNotNone(winning_answer.created_at)

        self.assertEqual('', winning_answer.content)
        self.assertEqual(None, winning_answer.message_id)

        # Now as the last test, the user should have 1 win in the stats menu
        await go_to_stats_menu(user)
        self.assertIn(f''
                      f'Nimi| V1| V2\n'
                      f'<><><><><><>\n'
                      f'{user_to_set_as_winner.username}   |  1|  1', chat.last_bot_txt())

    async def test_end_season_without_questions_season_is_deleted(self):
        chat, user = init_chat_user()
        await populate_season_v2(chat)

        # Ending season without questions deletes the season
        await go_to_main_menu(user)
        await user.press_button(end_season_btn)
        self.assertRegex(chat.last_bot_txt(), no_dq_season_deleted_msg)

        await go_to_main_menu(user)
        self.assertRegex(chat.last_bot_txt(), 'Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')

    #
    # Daily Question menu - Stats
    #

    @freeze_time('2023-01-02', as_arg=True)
    async def test_stats_should_show_season_status(clock: FrozenDateTimeFactory, self):  #NOSONAR (S5720)
        chat = MockChat()
        await populate_season_with_dq_and_answer_v2(chat)

        # As prepopulated user who has asked one question, check that their stats are shown
        # However, first question of the season is not included in the stats
        user1 = chat.users[-1]
        user2 = MockUser(chat=chat)

        await go_to_stats_menu(user1)
        self.assertIn('Kysymyksiä esitetty: 1', chat.last_bot_txt())
        self.assertIn(f'{user1.username}   |  0|  1', chat.last_bot_txt())

        # After single daily question, should be updated to 1 victory
        clock.tick(datetime.timedelta(days=1))
        dq_msg = await user1.send_message('#päivänkysymys')

        await go_to_stats_menu(user1)
        self.assertIn('Kysymyksiä esitetty: 2', chat.last_bot_txt())
        self.assertIn(f'{user1.username}   |  1|  1', chat.last_bot_txt())

        # Now simulate situation, where questions are bounced between 2 users
        clock.tick(datetime.timedelta(days=1))

        await user2.send_message('vastaus', reply_to_message=dq_msg)
        dq_msg = await user2.send_message('#päivänkysymys')
        clock.tick(datetime.timedelta(days=1))
        await user1.send_message('vastaus', reply_to_message=dq_msg)
        await user1.send_message('#päivänkysymys')

        await go_to_stats_menu(user1)
        self.assertIn('Kysymyksiä esitetty: 4', chat.last_bot_txt())
        self.assertIn(f'{user1.username}   |  2|  2', chat.last_bot_txt())
        self.assertIn(f'{user2.username}   |  1|  1', chat.last_bot_txt())

    @freeze_time('2023-01-02', as_arg=True)
    async def test_stats_should_be_calculated_based_on_presented_daily_questions(clock: FrozenDateTimeFactory, self):  #NOSONAR (S5720)
        chat = MockChat()
        await populate_season_v2(chat)

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
        await go_to_stats_menu(users[0])
        self.assertIn('Kysymyksiä esitetty: 6', chat.last_bot_txt())
        self.assertIn(f'{users[1].username}   |  3|  0', chat.last_bot_txt())
        self.assertIn(f'{users[0].username}   |  2|  0', chat.last_bot_txt())

    async def test_user_can_change_shown_season_with_inline_button_or_reply(self):
        """ Tests that when there are multiple seasons users can change season by pressing a button from
            the inline keyboard or by replying with a number. If user replies with a message that contains anything
            else than a number option that is available in the seasons roster, nothing happens """
        chat = MockChat()
        season_1 = await populate_season_with_dq_and_answer_v2(chat)
        season_1.end_datetime = datetime.datetime.now()  # Add end time to make season not active
        season_1.season_name = 'season_1'
        season_1.save()

        user = chat.users[-1]

        await go_to_main_menu(user)
        season_2 = await populate_season_with_dq_and_answer_v2(chat)
        season_2.season_name = 'season_2'
        season_2.save()

        # Now the seasons have been populated. Current season should be season 2
        await go_to_stats_menu(user)
        self.assertIn('Kausi: season_2', chat.last_bot_txt())
        assert_buttons_contain(self, chat.last_bot_msg(), '1: season_1')
        assert_buttons_contain(self, chat.last_bot_msg(), '[2]: season_2')

        # When user presses button to change season, it has changed
        await user.press_button_with_text('1: season_1')
        assert_buttons_contain(self, chat.last_bot_msg(), '2: season_2')
        self.assertIn('Kausi: season_1', chat.last_bot_txt())

        # Now, if user replies to the message nothing happens. User cannot change season with a reply.
        await user.send_message('2', reply_to_message=chat.last_bot_msg())
        await user.send_message('season_2', reply_to_message=chat.last_bot_msg())
        await user.send_message('', reply_to_message=chat.last_bot_msg())
        self.assertIn('Kausi: season_1', chat.last_bot_txt())

        # Pressing the same season button does nothing but reload the stats
        await user.press_button_with_text('[1]: season_1')
        self.assertIn('Kausi: season_1', chat.last_bot_txt())

        # Now for measure, change the season once more
        await user.press_button_with_text('2: season_2')
        self.assertIn('Kausi: season_2', chat.last_bot_txt())

    #
    # Daily Question menu - Stats - Exel exporter
    #

    async def test_exported_stats_excel(self):
        chat = MockChat()
        season = await populate_season_with_dq_and_answer_v2(chat)
        user = chat.users[-1]

        # Download excel. With ChatMockV2, document binary stream is saved to the chat objects document list
        # As CallbackContext.bot is not used in Mock v2 classes, mock is used
        await go_to_stats_menu(user)
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
        await populate_season_with_dq_and_answer_v2(chat)
        expected_str = [main_menu_basic_info,
                        'Valitse toiminto alapuolelta.',
                        'Päivän kysyjät 🧐']
        await self.navigate_all_menus_from_main_menu(chat, user, expected_str)

    async def navigate_all_menus_from_main_menu(self, chat, user, expected_str):
        await user.send_message(kysymys_command, chat)
        # Visit all 3 menu states and return to main menu
        if (DQMainMenuState._menu_text not in chat.last_bot_txt()
                and DQMainMenuState._no_seasons_text not in chat.last_bot_txt()):
            await user.press_button(back_button)

        await user.press_button(info_btn)
        self.assertIn(expected_str[0], chat.last_bot_txt())
        await user.press_button(back_button)

        self.assertIn(expected_str[1], chat.last_bot_txt())

        await user.press_button(stats_btn)
        self.assertIn(expected_str[2], chat.last_bot_txt())

    async def test_cancel_season_start_and_cancel_season_end_buttons(self):
        """ User should be able to cancel start and end season activities.
            When user cancels, they are returned to the 'main menu'."""
        # First test that user can cancel starting a season
        chat, user = init_chat_user()
        await user.send_message(kysymys_command)

        self.assertIn(DQMainMenuState._no_seasons_text, chat.last_bot_txt())
        await user.press_button(start_season_btn)
        await user.press_button(cancel_button)

        # Now user should be returned to the main menu and the main menu contains
        # information that creating season has been cancelled. As no season has yet
        # been created, informs user about that.
        expected = ("[  Päivän kysymys  ]\n\n"
                    "Kysymyskauden aloittaminen peruutettu.\n"
                    "\n"
                    "Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille. "
                    "Aloita luomalla kysymyskausi alla olevalla toiminnolla.")
        self.assertEqual(expected, chat.last_bot_txt())

        seasons = DailyQuestionSeason.objects.all()
        self.assertSequenceEqual([], list(seasons))

        # Then test that user can cancel ending a season
        await populate_season_with_dq_and_answer_v2(chat)

        await user.send_message(kysymys_command)
        await user.press_button(back_button)
        await user.press_button(end_season_btn)
        await user.press_button(cancel_button)

        # Now should inform that ending season cancelled. In addition, now that the chat has
        # daily question season created, should just prompt user to select actions
        expected = ("[  Päivän kysymys  ]\n\n"
                    "Kysymyskauden päättäminen peruutettu.\n"
                    "\n"
                    "Valitse toiminto alapuolelta.")
        self.assertEqual(expected, chat.last_bot_txt())
        season = DailyQuestionSeason.objects.first()
        self.assertIsNone(season.end_datetime)

    #
    # Daily Question menu - Misc / Other
    #

    async def test_when_next_day_dq_has_been_asked_end_season_gives_its_date_as_button(self):
        chat = MockChat()
        await populate_season_with_dq_and_answer_v2(chat)
        user = chat.users[-1]

        # User sends new daily question. As today already has one, it is set to be next days question
        await user.send_message('#päivänkysymys dato_of_question should be next day')
        last_dq = DailyQuestion.objects.last()
        self.assertIn('2023-01-03', str(last_dq.date_of_question))

        # Now if user wants to end season, it cannot be ended before the date of latest dq
        await go_to_main_menu(user)
        await user.press_button(end_season_btn)
        await user.press_button_with_text(user.username)  # Select user as the winnier of the last question

        # Test that bot gives button with next days date as it's the last date with daily question
        assert_buttons_equals(self, ['Peruuta ❌', 'ma 03.01.2023'], chat.last_bot_msg())

        # Try to make season end today. Should give error
        await user.reply_to_bot('02.01.2023')
        expected_reply = 'Kysymyskausi voidaan merkitä päättyneeksi aikaisintaan viimeisen esitetyn päivän kysymyksen päivänä'
        self.assertIn(expected_reply, chat.last_bot_txt())
        await user.press_button_with_text('ma 03.01.2023')
        self.assertIn('Kysymyskausi merkitty päättyneeksi 03.01.2023', chat.last_bot_txt())
        self.assertIn('2023-01-03', str(DailyQuestionSeason.objects.first().end_datetime))

    #
    # Daily Question Scheduled message content
    #
    async def test_daily_question_create_message_board_message(self):
        chat = MockChat()
        await populate_season_with_dq_and_answer_v2(chat)
        expected_board_message = ('Päivän kysyjät 🧐\n'
                                  '\n'
                                  'Kausi: season_name\n'
                                  'Kausi alkanut: 02.01.2023\n'
                                  'Kysymyksiä esitetty: 1\n'
                                  '```\n'
                                  'Nimi| V1| V2\n'
                                  '<><><><><><>\n'
                                  f'{chat.users[-1].username}   |  0|  1\n'
                                  '```\n'
                                  'V1=Voitot, V2=Vastaukset')

        actual_board_message: MessageBoardMessage = await daily_question_menu_states.create_message_board_msg(
            None, chat.id)
        self.assertEqual(expected_board_message, actual_board_message.body)

    async def test_daily_question_create_message_board_message_no_active_season(self):
        chat, user = init_chat_user()
        await user.send_message('test')

        actual_board_message: MessageBoardMessage = await daily_question_menu_states.create_message_board_msg(
            None, chat.id)
        self.assertEqual(None, actual_board_message)

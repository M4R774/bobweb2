from datetime import datetime, date
from typing import List
import io

from telegram.ext import CallbackContext

from django.db.models import QuerySet
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
import xlsxwriter

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState, back_button
from bobweb.bob.activities.common_activity_states import PaginatorState
from bobweb.bob.activities.daily_question.dq_excel_exporter_v2 import send_dq_stats_excel_v2
from bobweb.bob.activities.daily_question.end_season_states import SetLastQuestionWinnerState
from bobweb.bob.activities.daily_question.start_season_states import SetSeasonStartDateState
from bobweb.bob.database import find_dq_season_ids_for_chat
from bobweb.bob.resources.bob_constants import EXCEL_DATETIME_FORMAT, ISO_DATE_FORMAT, fitz, FILE_NAME_DATE_FORMAT
from bobweb.bob.utils_common import has, has_no, fitzstr_from, fitz_from, excel_time, excel_date
from bobweb.bob.utils_format import MessageArrayFormatter
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestionAnswer, TelegramUser, DailyQuestion

#
# static buttons
#

# DQMainMenuState
info_btn = InlineKeyboardButton(text='Info ⁉', callback_data='/info')
season_btn = InlineKeyboardButton(text='Kausi 📅', callback_data='/season')
stats_btn = InlineKeyboardButton(text='Tilastot 📊', callback_data='/stats')

# DQSeasonsMenuState
end_season_btn = InlineKeyboardButton(text='Lopeta kausi 🏁', callback_data='/end_season')
start_season_btn = InlineKeyboardButton(text='Aloita kausi 🚀', callback_data='/start_season')

# DQStatsMenuState
get_xlsx_btn = InlineKeyboardButton(text='Lataa xlsx-muodossa 💾', callback_data='/get_xlsx')


class DQMainMenuState(ActivityState):
    def execute_state(self):
        reply_text = dq_main_menu_text_body('Valitse toiminto alapuolelta')
        markup = InlineKeyboardMarkup(self.dq_main_menu_buttons())
        self.activity.reply_or_update_host_message(reply_text, markup)

    def dq_main_menu_buttons(self):
        return [[info_btn, season_btn, stats_btn]]

    def handle_response(self, response_data: str, context: CallbackContext = None):
        next_state: ActivityState | None = None
        match response_data:
            case info_btn.callback_data:
                next_state = DQInfoMessageState()
            case season_btn.callback_data:
                next_state = DQSeasonsMenuState()
            case stats_btn.callback_data:
                next_state = DQStatsMenuState()

        if next_state:
            self.activity.change_state(next_state)


class DQInfoMessageState(ActivityState):
    def execute_state(self):
        reply_text = dq_main_menu_text_body(main_menu_basic_info)
        markup = InlineKeyboardMarkup([[back_button]])
        self.activity.reply_or_update_host_message(reply_text, markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        match response_data:
            case back_button.callback_data:
                self.activity.change_state(DQMainMenuState())


main_menu_basic_info = \
    'Päivän kysymys on peli, missä kysymysvuorossa oleva pelaaja esittää minkä vain vapaavalintaisen ' \
    'kysymyksen muulle ryhmälle. Muut ryhmäläiset vastaavat kysymykseen ja kysymyken voittanut ' \
    'pelaaja voi esittää seuraavana arkipäivänä seuraavan päivän kysymyksen. Bob pitää ' \
    'automaattisesti kirjaa kaikista ryhmässä esitetyistä päivän kysymyksistä ja vastauksista niihin' \
    '\n\n' \
    'Vastaus tulkitaan päivän kysymykseksi, jos se sisältää tägin \'päivänkysymys\'. Tällöin ' \
    'kyseisen viestin ja kaikkien siihen annettujen vastausten sisältö tallennetaan myöhempää ' \
    'tarkastelua varten. Kun käyttäjä esittää päivän kysymyksen, hänen edelliseen viestiin antamansa ' \
    'viesti merkitään automaattisesti voittaneeksi vastaukseksi.'


class DQSeasonsMenuState(ActivityState):
    def execute_state(self):
        seasons = database.find_dq_seasons_for_chat(self.activity.host_message.chat_id)
        if has(seasons):
            self.handle_has_seasons(seasons)
        else:
            self.handle_has_no_seasons()

    def handle_has_seasons(self, seasons: QuerySet):
        latest_season: DailyQuestionSeason = seasons.first()

        season_info = get_season_basic_info_text(latest_season)
        end_or_start_button = end_season_btn if latest_season.end_datetime is None else start_season_btn
        markup = InlineKeyboardMarkup([[back_button, end_or_start_button]])
        self.activity.reply_or_update_host_message(season_info, markup)

    def handle_has_no_seasons(self):
        reply_text = dq_main_menu_text_body('Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')
        markup = InlineKeyboardMarkup([[back_button, start_season_btn]])
        self.activity.reply_or_update_host_message(reply_text, markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        match response_data:
            case back_button.callback_data:
                self.activity.change_state(DQMainMenuState())
            case start_season_btn.callback_data:
                self.activity.change_state(SetSeasonStartDateState())
            case end_season_btn.callback_data:
                self.activity.change_state(SetLastQuestionWinnerState())


def get_season_basic_info_text(season: DailyQuestionSeason):
    questions = database.get_all_dq_on_season(season.id)
    winning_answers_on_season = database.find_answers_in_season(season.id).filter(is_winning_answer=True)

    most_wins_text = get_most_wins_text(winning_answers_on_season)

    fitz_end_dt = ''
    season_state = 'Aktiivisen'
    if has(season.end_datetime):
        season_state = 'Edellisen'
        fitz_end_dt = f'Kausi päättynyt: {fitzstr_from(season.end_datetime)}\n'

    return dq_main_menu_text_body(f'Kysymyskaudet\n'
                                  f'{season_state} kauden nimi: {season.season_name}\n'
                                  f'Kausi alkanut: {fitzstr_from(season.start_datetime)}\n'
                                  f'{fitz_end_dt}'
                                  f'Kysymyksiä kysytty: {questions.count()}\n'
                                  f'{most_wins_text}')


def get_most_wins_text(winning_answers: QuerySet) -> str:
    if has_no(winning_answers):
        return ''

    # https://dev.to/mojemoron/pythonic-way-to-aggregate-or-group-elements-in-a-list-using-dict-get-and-dict-setdefault-49cb
    wins_by_users = {}
    for answer in winning_answers:
        name = answer.answer_author.username
        wins_by_users[name] = wins_by_users.get(name, 0) + 1

    max_wins = max([x for x in list(wins_by_users.values())])
    users_with_most_wins = [user for (user, wins) in wins_by_users.items() if wins == max_wins]

    if len(users_with_most_wins) <= 3:
        return f'Eniten voittoja ({max_wins}): {", ".join(users_with_most_wins)}'
    else:
        return f'Eniten voittoja ({max_wins}): {len(users_with_most_wins)} käyttäjää'


def dq_main_menu_text_body(state_message_provider):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider()
    return f'-- Päivän kysymys (🅱️eta) --\n' \
           f'------------------\n' \
           f'{state_msg}'


def get_stats_state_buttons():
    return [[back_button, get_xlsx_btn]]


class DQStatsMenuState(ActivityState):
    def __init__(self):
        super().__init__()
        self.chats_seasons = []
        self.paginator = None

    def execute_state(self):
        self.chats_seasons: list[int] = find_dq_season_ids_for_chat(self.activity.host_message.chat_id)
        count = len(self.chats_seasons)

        if count == 0:
            markup = InlineKeyboardMarkup([[back_button]])
            self.activity.reply_or_update_host_message("Ei lainkaan kysymyskausia.", markup)
            return

        if self.paginator is None:
            self.paginator = PaginatorState(self.send_simple_stats_for_season, count, count - 1, get_stats_state_buttons)
            self.paginator.activity = self.activity  # Share same activity

        self.paginator.execute_state()

    def send_simple_stats_for_season(self, page_number: int):
        """
        Base logic. Each asked daily question means that the user won previous daily question
        (excluding first question of the season). This calculates how many question each
        user has asked and lists the scores in a sorted array
        """
        season_id = self.chats_seasons[page_number - 1].get('id')
        season: DailyQuestionSeason = database.get_dq_season(season_id)

        answers_on_season: List[DailyQuestionAnswer] = list(database.find_answers_in_season(season.id))
        dq_on_season: List[DailyQuestion] = get_all_but_first_dq_in_season(season.id)

        # Get unique values by list -> set -> list
        users = list(set([a.answer_author for a in answers_on_season] + [dq.question_author for dq in dq_on_season]))

        # First make list of rows. Each row is single users data
        member_array = create_member_array(users, answers_on_season, dq_on_season)
        # Add heading row
        member_array.insert(0, ['Nimi', 'V1', 'V2'])

        formatter = MessageArrayFormatter('| ', '<>').with_truncation(28, 0)
        formatted_members_array_str = formatter.format(member_array)

        footer = 'V1=Voitot, V2=Vastaukset'

        msg_body = 'Päivän kysyjät \U0001F9D0\n\n' \
                   + f'Kausi: {season.season_name}\n' \
                   + f'Kysymyksiä esitetty: {season.dailyquestion_set.count()}\n\n' \
                   + f'```\n' \
                   + f'{formatted_members_array_str}' \
                   + f'```\n' \
                   + f'{footer}'
        return dq_main_menu_text_body(msg_body)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        match response_data:
            case back_button.callback_data:
                self.activity.change_state(DQMainMenuState())
                return
            case get_xlsx_btn.callback_data:
                send_dq_stats_excel_v2(self.activity.host_message.chat_id, context)
                return

        # Response not handled by this state. Propagate to the paginator to handle
        self.paginator.handle_response(response_data, context)


excel_sheet_headings = ['Kauden nimi', 'Kauden aloitus', 'Kauden Lopetus',
                        'Kysymyksen päivä', 'Kysymyksen luontiaika', 'Kysyjä', 'Kysymysviestin sisältö',
                        'Vastauksen luontiaika', 'Vastaaja', 'Vastauksen sisältö', 'Voittanut vastaus']


def get_all_but_first_dq_in_season(season_id):
    dq_on_season: List[DailyQuestion] = list(database.get_all_dq_on_season(season_id))
    # Remove first question of the season
    if len(dq_on_season) == 1:
        dq_on_season = []
    else:
        dq_on_season = dq_on_season[:-1]
    return dq_on_season


def create_member_array(users: List[TelegramUser], all_a: List[DailyQuestionAnswer], dq_list: List[DailyQuestion]):
    wins_by_user: dict = {}
    for dq in dq_list:
        wins_by_user[dq.question_author.id] = wins_by_user.get(dq.question_author.id, 0) + 1

    users_array = []
    for user in users:
        # As multiple messages might be saves as users answer, get list of first answers
        users_answers = [a for a in all_a if a.answer_author == user]
        q_answered = single_a_per_q(users_answers)
        users_answer_count = len(q_answered)
        users_win_count = wins_by_user.get(user.id, 0)
        user_name = user.username if has(user.username) else f'{user.first_name} {user.last_name}'
        row = [str(user_name), users_win_count, users_answer_count]
        users_array.append(row)

    # Sort users in order of wins [desc], then answers [asc]
    users_array.sort(key=lambda row: (-row[1], row[2]))
    return users_array


def single_a_per_q(answers: List[DailyQuestionAnswer]):
    a_per_q = dict()
    for a in answers:
        # If answers question not yet in dict or the answer is winning one, add it to the dict
        if a.question not in a_per_q or a.is_winning_answer:
            a_per_q[a.question] = a
    return list(a_per_q)


def write_array_to_sheet(array: List[List[str]], sheet):
    for i, row in enumerate(array):
        for j, cell in enumerate(row):
            sheet.write(i, j, str(cell))

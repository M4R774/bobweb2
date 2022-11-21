from datetime import datetime, date
from typing import List
import io

from telegram.ext import CallbackContext
from xlsxwriter import Workbook

from django.db.models import QuerySet
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton

from bobweb.bob import database, command_service
from bobweb.bob.activities.activity_state import ActivityState, back_button
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.daily_question.end_season_states import SetLastQuestionWinnerState
from bobweb.bob.activities.daily_question.start_season_activity import StartSeasonActivity
from bobweb.bob.activities.daily_question.start_season_states import SetSeasonStartDateState
from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT, EXCEL_DATETIME_FORMAT, ISO_DATE_FORMAT
from bobweb.bob.utils_common import has, has_no
from bobweb.bob.utils_format import MessageArrayFormatter
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestionAnswer, TelegramUser, DailyQuestion


class DQMainMenuState(ActivityState):
    def __init__(self, activity: CommandActivity = None, initial_update: Update = None):
        super().__init__()
        self.activity = activity
        self.initial_update = initial_update

    def execute_state(self):
        reply_text = dq_main_menu_text_body('Valitse toiminto alapuolelta')
        markup = InlineKeyboardMarkup(self.dq_main_menu_buttons())

        if self.activity.host_message is None:
            self.activity.host_message = self.initial_update.effective_message.reply_text(reply_text, reply_markup=markup)
        else:
            self.activity.update_host_message_content(reply_text, markup)

    def dq_main_menu_buttons(self):
        return [[
            InlineKeyboardButton(text='Info', callback_data='/info'),
            InlineKeyboardButton(text='Kausi', callback_data='/season'),
            InlineKeyboardButton(text='Tilastot', callback_data='/stats')
        ]]

    def handle_response(self, response_data: str, context: CallbackContext = None):
        next_state: ActivityState | None = None
        match response_data:
            case '/info': next_state = DQInfoMessageState()
            case '/season': next_state = DQSeasonsMenuState()
            case '/stats': next_state = DQStatsMenuState(self.initial_update)

        if next_state:
            self.activity.change_state(next_state)


class DQInfoMessageState(ActivityState):
    def execute_state(self):
        info_text = 'Päivän kysymys on peli, missä kysymysvuorossa oleva pelaaja esittää minkä vain vapaavalintaisen ' \
                    'kysymyksen muulle ryhmälle. Muut ryhmäläiset vastaavat kysymykseen ja kysymyken voittanut ' \
                    'pelaaja voi esittää seuraavana arkipäivänä seuraavan päivän kysymyksen. Bob pitää ' \
                    'automaattisesti kirjaa kaikista ryhmässä esitetyistä päivän kysymyksistä ja vastauksista niihin' \
                    '\n\n' \
                    'Vastaus tulkitaan päivän kysymykseksi, jos se sisältää tägin \'päivänkysymys\'. Tällöin ' \
                    'kyseisen viestin ja kaikkien siihen annettujen vastausten sisältö tallennetaan myöhempää ' \
                    'tarkastelua varten. Kun käyttäjä esittää päivän kysymyksen, hänen edelliseen viestiin antamansa ' \
                    'viesti merkitään automaattisesti voittaneeksi vastaukseksi.'
        reply_text = dq_main_menu_text_body(info_text)
        markup = InlineKeyboardMarkup([[back_button]])
        self.activity.update_host_message_content(reply_text, markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        extended_info_text = None
        match response_data:
            case back_button.callback_data:
                self.activity.change_state(DQMainMenuState())
        self.activity.update_host_message_content(extended_info_text)


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
        if latest_season.end_datetime is None:
            end_or_start_button = InlineKeyboardButton(text='Lopeta kausi', callback_data='/end_season')
        else:
            end_or_start_button = InlineKeyboardButton(text='Aloita kausi', callback_data='/start_season')

        buttons = [[
            back_button,
            end_or_start_button
        ]]
        self.activity.update_host_message_content(season_info, InlineKeyboardMarkup(buttons))

    def handle_has_no_seasons(self):
        reply_text = dq_main_menu_text_body('Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')
        buttons = [[
            back_button,
            InlineKeyboardButton(text='Aloita kausi', callback_data='/start_season')
        ]]
        self.activity.update_host_message_content(reply_text, InlineKeyboardMarkup(buttons))

    def handle_response(self, response_data: str, context: CallbackContext = None):
        match response_data:
            case back_button.callback_data:
                self.activity.change_state(DQMainMenuState())
            case '/start_season':
                # Example of changing Activity to a different activity that has different base class
                host_message = self.activity.host_message
                self.activity.done()  # Mark current activity to be done
                self.activity = StartSeasonActivity()
                command_service.instance.add_activity(self.activity)  # Add to commandService current_activites
                self.activity.host_message = host_message
                self.activity.change_state(SetSeasonStartDateState())
            case '/end_season':
                # Example of keeping same activity but just changing its state
                self.activity.change_state(SetLastQuestionWinnerState())


def get_season_basic_info_text(season: DailyQuestionSeason):
    questions = database.get_all_dq_on_season(season.id)
    winning_answers_on_season = database.find_answers_in_season(season.id).filter(is_winning_answer=True)

    most_wins_text = get_most_wins_text(winning_answers_on_season)

    conditional_end_date = ''
    season_state = 'Aktiivisen'
    if has(season.end_datetime):
        season_state = 'Edellisen'
        conditional_end_date = f'Kausi päättynyt: {season.end_datetime.strftime(FINNISH_DATE_FORMAT)}\n'

    return dq_main_menu_text_body(f'Kysymyskaudet\n'
                                  f'{season_state} kauden nimi: {season.season_name}\n'
                                  f'Kausi alkanut: {season.start_datetime.strftime(FINNISH_DATE_FORMAT)}\n'
                                  f'{conditional_end_date}'
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
    return f'-- Päivän kysymys (Beta) --\n' \
           f'------------------\n' \
           f'{state_msg}'


class DQStatsMenuState(ActivityState):
    def execute_state(self):
        self.send_simple_stats_for_active_season()

    def send_simple_stats_for_active_season(self):
        host_message = self.activity.host_message
        current_season: DailyQuestionSeason = database.find_active_dq_season(host_message.chat.id,
                                                                             host_message.date).first()
        if has_no(current_season):
            self.activity.update_host_message_content("Ei aktiivista kysymyskautta.")
            return

        answers_on_season: List[DailyQuestionAnswer] = list(database.find_answers_in_season(current_season.id))
        users = list(set([a.answer_author for a in answers_on_season]))  # Get unique values by list -> set -> list

        headings = ['Nimi', 'V1', 'V2']
        # First make list of rows. Each row is single users data
        member_array = create_member_array(users, answers_on_season)
        member_array.insert(0, headings)

        formatter = MessageArrayFormatter('| ', '<>').with_truncation(28, 0)
        formatted_members_array_str = formatter.format(member_array)

        footer = 'V1=Voitot, V2=Vastaukset'

        reply_text = '```\n' \
                     + 'Päivän kysyjät \U0001F9D0\n\n' \
                     + f'Kausi: {current_season.season_name}\n' \
                       f'Kysymyksiä esitetty: {current_season.dailyquestion_set.count()}\n\n' \
                     + f'{formatted_members_array_str}\n' \
                     + f'{footer}' \
                     + '```'  # '\U0001F913' => nerd emoji, '```' =>  markdown code block start/end

        buttons = [[
            back_button,
            InlineKeyboardButton(text='Lataa xlsx-muodossa', callback_data='/get_xlsx')
        ]]
        self.activity.update_host_message_content(reply_text, InlineKeyboardMarkup(buttons))

    def handle_response(self, response_data: str, context: CallbackContext = None):
        match response_data:
            case back_button.callback_data:
                self.activity.change_state(DQMainMenuState())
            case '/get_xlsx':
                self.send_dq_stats_excel(context)

    def send_dq_stats_excel(self, context: CallbackContext = None):
        stats_array = create_chat_dq_stats_array(self.activity.host_message.chat_id)

        output = io.BytesIO()
        workbook = Workbook(output)
        sheet = workbook.add_worksheet("Kysymystilastot")
        write_array_to_sheet(stats_array, sheet)
        workbook.close()
        output.seek(0)

        today_date_iso_str = datetime.today().date().strftime(ISO_DATE_FORMAT)
        file_name = f'{today_date_iso_str}_daily_question_stats.xlsx'
        context.bot.send_document(document=output, filename=file_name)


def create_chat_dq_stats_array(chat_id: int):
    all_seasons: List[DailyQuestionSeason] = database.get_seasons_for_chat(chat_id)
    headings = ['Kauden nimi', 'Kauden aloitus', 'Kauden Lopetus',
                'Kysymyksen päivä', 'Kysymyksen luontiaika', 'Kysyjä', 'Kysymysviestin sisältö',
                'Vastauksen luontiaika', 'Vastaaja', 'Vastauksen sisältö', 'Voittanut vastaus']
    result_array = [headings]  #
    for s in all_seasons:
        end_datetime_str = excel_time(s.end_datetime) if has(s.end_datetime) else ''
        season = [s.season_name, excel_time(s.start_datetime), end_datetime_str]
        all_questions: List[DailyQuestion] = list(s.dailyquestion_set.all())
        for q in all_questions:
            question = [excel_date(q.date_of_question.date()), excel_time(q.created_at), q.question_author, q.content]
            all_answers: List[DailyQuestionAnswer] = list(q.dailyquestionanswer_set.all())
            for a in all_answers:
                answer = [excel_time(a.created_at), a.answer_author, a.content, a.is_winning_answer]

                row = season + question + answer
                result_array.append(row)
    print(result_array)
    return result_array


def excel_time(d: datetime) -> str:
    return d.strftime(EXCEL_DATETIME_FORMAT)  # -> '2022-09-24 10:18:32'


def excel_date(d: date) -> str:
    return d.strftime(ISO_DATE_FORMAT)  # -> '2022-09-24'


def create_member_array(users: List[TelegramUser], all_a: List[DailyQuestionAnswer]):
    users_array = []
    for user in users:
        # As multiple messages might be saves as users answer, get list of first answers
        users_answers = [a for a in all_a if a.answer_author == user]
        q_answered = single_a_per_q(users_answers)
        users_a_count = len(q_answered)
        users_w_count = len([a for a in users_answers if a.is_winning_answer])
        row = [str(user.username), users_w_count, users_a_count]
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

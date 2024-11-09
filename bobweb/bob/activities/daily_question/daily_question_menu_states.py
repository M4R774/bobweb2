import re
from typing import List, Tuple

from telegram.ext import CallbackContext

from django.db.models import QuerySet
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.constants import ParseMode

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState, back_button
from bobweb.bob.activities.daily_question.dq_excel_exporter_v2 import send_dq_stats_excel_v2
from bobweb.bob.activities.daily_question.end_season_states import SetLastQuestionWinnerState
from bobweb.bob.activities.daily_question.start_season_states import SetSeasonStartDateState
from bobweb.bob.database import find_dq_season_ids_for_chat, SeasonListItem
from bobweb.bob.utils_common import has, has_no, fitzstr_from, split_to_chunks, send_bot_is_typing_status_update
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
    _menu_text = 'Valitse toiminto alapuolelta'

    async def execute_state(self):
        reply_text = dq_main_menu_text_body(DQMainMenuState._menu_text)
        markup = InlineKeyboardMarkup(self.dq_main_menu_buttons())
        await self.send_or_update_host_message(reply_text, markup)

    def dq_main_menu_buttons(self):
        return [[info_btn, season_btn, stats_btn]]

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        next_state: ActivityState | None = None
        match response_data:
            case info_btn.callback_data:
                next_state = DQInfoMessageState()
            case season_btn.callback_data:
                next_state = DQSeasonsMenuState()
            case stats_btn.callback_data:
                next_state = DQStatsMenuState()

        if next_state:
            await self.activity.change_state(next_state)


class DQInfoMessageState(ActivityState):
    async def execute_state(self):
        reply_text = dq_main_menu_text_body(main_menu_basic_info)
        markup = InlineKeyboardMarkup([[back_button]])
        await self.send_or_update_host_message(reply_text, markup)

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        match response_data:
            case back_button.callback_data:
                await self.activity.change_state(DQMainMenuState())


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
    async def execute_state(self):
        await send_bot_is_typing_status_update(self.activity.initial_update.effective_chat)
        seasons = database.find_dq_seasons_for_chat(self.get_chat_id())
        if has(seasons):
            await self.handle_has_seasons(seasons)
        else:
            await self.handle_has_no_seasons()

    async def handle_has_seasons(self, seasons: QuerySet):
        latest_season: DailyQuestionSeason = seasons.first()

        season_info = get_season_basic_info_text(latest_season)
        end_or_start_button = end_season_btn if latest_season.end_datetime is None else start_season_btn
        markup = InlineKeyboardMarkup([[back_button, end_or_start_button]])
        await self.send_or_update_host_message(season_info, markup)

    async def handle_has_no_seasons(self):
        reply_text = dq_main_menu_text_body('Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')
        markup = InlineKeyboardMarkup([[back_button, start_season_btn]])
        await self.send_or_update_host_message(reply_text, markup)

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        match response_data:
            case back_button.callback_data:
                await self.activity.change_state(DQMainMenuState())
            case start_season_btn.callback_data:
                await self.activity.change_state(SetSeasonStartDateState())
            case end_season_btn.callback_data:
                await self.activity.change_state(SetLastQuestionWinnerState())


def get_season_basic_info_text(season: DailyQuestionSeason):
    question_count = database.get_dq_count_on_season(season.id)
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
                                  f'Kysymyksiä kysytty: {question_count}\n'
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
    return f'[  Päivän kysymys  ]\n\n' \
           f'{state_msg}'


def get_stats_state_buttons():
    return [[back_button, get_xlsx_btn]]


def parse_integer_or_none(input_string: str) -> int | None:
    try:
        return int(input_string)
    except Exception:
        return None


class DQStatsMenuState(ActivityState):
    def __init__(self, chats_seasons: List[SeasonListItem] = None):
        super().__init__()
        # chats seasons: List of chat's seasons id's
        self.chats_seasons: List[SeasonListItem] = chats_seasons
        self.current_season_id = None

    async def execute_state(self):
        await send_bot_is_typing_status_update(self.activity.initial_update.effective_chat)
        if self.chats_seasons is None:
            self.chats_seasons: List[SeasonListItem] = find_dq_season_ids_for_chat(self.get_chat_id())
        count = len(self.chats_seasons)

        if count == 0:
            markup = InlineKeyboardMarkup([[back_button]])
            await self.send_or_update_host_message("Ei lainkaan kysymyskausia.", markup)
            return

        await self.create_stats_message_and_send_to_chat(count)

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        # Only trigger if inline button is pressed. Users replies are not reacted to
        if update.callback_query:
            match update.callback_query.data:
                case back_button.callback_data:
                    await self.activity.change_state(DQMainMenuState())
                    return
                case get_xlsx_btn.callback_data:
                    await send_bot_is_typing_status_update(self.activity.initial_update.effective_chat)
                    await send_dq_stats_excel_v2(self.get_chat_id(), self.current_season_id, context)
                    return
                case _:
                    # Then check if the callback-data contains number that is available in the menu.
                    # Only then switch the season
                    data_int = parse_integer_or_none(update.callback_query.data)
                    chats_season_ordinal_numbers = [season.ordinal_number for season in self.chats_seasons]
                    if data_int in chats_season_ordinal_numbers:
                        await self.create_stats_message_and_send_to_chat(data_int)

    async def create_stats_message_and_send_to_chat(self, season_number: int):
        target_season = self.chats_seasons[season_number - 1]
        if self.current_season_id == target_season.id:
            return  # Nothing to update
        self.current_season_id = target_season.id

        season_buttons = []
        for season in self.chats_seasons:
            # Add brackets to the current season label
            ordinal_number_str = f'[{season.ordinal_number}]' if season.ordinal_number == season_number else season.ordinal_number
            label = f'{ordinal_number_str}: {season.name}'
            season_buttons.append(InlineKeyboardButton(text=label, callback_data=season.ordinal_number))

        season_button_chunks = split_to_chunks(season_buttons, 2)

        text_content = create_stats_for_season(target_season.id)
        markup = InlineKeyboardMarkup(season_button_chunks + [[back_button, get_xlsx_btn]])
        await self.send_or_update_host_message(text=text_content, markup=markup, parse_mode=ParseMode.MARKDOWN)


def create_stats_for_season(season_id: int):
    """
    Base logic. Each asked daily question means that the user won previous daily question
    (excluding first question of the season). This calculates how many question each
    user has asked and lists the scores in a sorted array. For the last question of the season,
    winner is determined by the answer marked as the winning answer of the last question.
    """
    season: DailyQuestionSeason = database.get_dq_season(season_id)

    answers_on_season: List[DailyQuestionAnswer] = list(database.find_answers_in_season(season.id))
    dq_on_season: List[DailyQuestion] = list(database.get_all_dq_on_season(season_id))
    users_on_chat: List[TelegramUser] = database.list_tg_users_for_chat(season.chat_id)

    # First make list of rows. Each row is single users data
    member_array = create_member_array(dq_on_season, answers_on_season, users_on_chat)
    # Add heading row
    member_array.insert(0, ['Nimi', 'V1', 'V2'])

    formatter = MessageArrayFormatter('| ', '<>').with_truncation(28, 0)
    formatted_members_array_str = formatter.format(member_array)

    footer = 'V1=Voitot, V2=Vastaukset\nVoit valita toisen kauden tarkasteltavaksi alapuolelta.'

    msg_body = 'Päivän kysyjät \U0001F9D0\n\n' \
               + f'Kausi: {season.season_name}\n' \
               + f'Kysymyksiä esitetty: {season.dailyquestion_set.count()}\n' \
               + f'```\n' \
               + f'{formatted_members_array_str}' \
               + f'```\n' \
               + f'{footer}'
    return msg_body


def create_member_array(dq_list: List[DailyQuestion],
                        answers: List[DailyQuestionAnswer],
                        users_on_chat: List[TelegramUser]) -> List[Tuple[str, int, int]]:
    wins_by_user: dict = {}
    answers_by_user: dict = {}
    for i, dq in enumerate(dq_list):
        # Wins are calculated by iterating through all daily questions. For each, it's authors win amount
        # (or default value of 0) is fetched from the dict, and it is incremented by one.
        # Exception: For the first question of the season no point is given.
        if i > 0:
            wins_by_user[dq.question_author.id] = wins_by_user.get(dq.question_author.id, 0) + 1

        # Calculate answers by iterating through answers for the question
        users_with_answers_set = set(())
        for answer in [a for a in answers if a.question_id == dq.id]:
            users_with_answers_set.add(answer.answer_author)

        # Add one answer for each user
        for user in users_with_answers_set:
            answers_by_user[user.id] = answers_by_user.get(user.id, 0) + 1

    # As the last question winner does not ask a question, it is determined by the answer
    # marked as the winning one for the last question. Normally this is asked when the season is ended.
    if dq_list:
        last_question = dq_list[-1]
        last_dq_winning_answer_author_id = next((a.answer_author.id for a in answers
                                                 if a.is_winning_answer and a.question_id == last_question.id), None)
        if last_dq_winning_answer_author_id:
            # Now add one win for the last question winner
            wins_by_user[last_dq_winning_answer_author_id] = wins_by_user.get(last_dq_winning_answer_author_id, 0) + 1

    all_participated_user_ids = wins_by_user.keys() | answers_by_user.keys()
    users_array = []
    for user_id in all_participated_user_ids:
        # As multiple messages might be saved as users answer, get list of first answers
        users_answer_count = answers_by_user.get(user_id, 0)
        users_win_count = wins_by_user.get(user_id, 0)
        user_entity = next((u for u in users_on_chat if u.id == user_id), None)
        user_name = get_printed_name(user_entity) if user_entity else str(user_id)
        user_row = (str(user_name), users_win_count, users_answer_count)
        users_array.append(user_row)

    # Sort users in order of wins [desc], then answers [asc]
    users_array.sort(key=lambda row: (-row[1], row[2]))
    return users_array


def get_printed_name(user: TelegramUser) -> str:
    if has(user.username):
        return f'{user.username}'
    else:
        return f'{user.first_name} {user.last_name}'


def write_array_to_sheet(array: List[List[str]], sheet):
    for i, row in enumerate(array):
        for j, cell in enumerate(row):
            sheet.write(i, j, str(cell))

import math
import random
import re
from datetime import datetime
from typing import List, Tuple, Optional

from django.db.models import QuerySet
from pytz import utc
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import database, utils_common
from bobweb.bob.activities.activity_state import ActivityState, cancel_button
from bobweb.bob.activities.activity_state import back_button
from bobweb.bob.activities.daily_question.date_confirmation_states import date_invalid_format_text
from bobweb.bob.activities.daily_question.dq_excel_exporter_v2 import send_dq_stats_excel_v2
from bobweb.bob.database import find_dq_season_ids_for_chat, SeasonListItem
from bobweb.bob.message_board import MessageBoardMessage, MessageBoard
from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.resources.unicode_emoji import get_random_number_of_emoji
from bobweb.bob.utils_common import dt_at_midday, parse_dt_str_to_utctzstr
from bobweb.bob.utils_common import send_bot_is_typing_status_update
from bobweb.bob.utils_common import split_to_chunks, has_no, has, fitzstr_from, fi_short_day_name, fitz_from
from bobweb.bob.utils_format import MessageArrayFormatter
from bobweb.web.bobapp.models import DailyQuestionAnswer, TelegramUser
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion

#
# static buttons
#

# DQMainMenuState
info_btn = InlineKeyboardButton(text='Info ⁉', callback_data='/info')
stats_btn = InlineKeyboardButton(text='Tilastot 📊', callback_data='/stats')
end_season_btn = InlineKeyboardButton(text='Lopeta kausi 🏁', callback_data='/end_season')
start_season_btn = InlineKeyboardButton(text='Aloita kausi 🚀', callback_data='/start_season')

# DQStatsMenuState
get_xlsx_btn = InlineKeyboardButton(text='Lataa xlsx-muodossa 💾', callback_data='/get_xlsx')


class DQMainMenuState(ActivityState):
    _menu_text = 'Valitse toiminto alapuolelta.'
    _no_seasons_text = ('Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille. '
                        'Aloita luomalla kysymyskausi alla olevalla toiminnolla.')

    def __init__(self, activity: 'CommandActivity' = None, additional_text: str | None = None):
        super().__init__(activity)
        self.additional_text: str | None = additional_text

    async def execute_state(self):
        seasons = database.find_dq_seasons_for_chat_order_id_desc(self.get_chat_id())
        menu_text = self._menu_text
        if not seasons:
            # If chat has no seasons at all
            menu_text = self._no_seasons_text

        # If this state was created with additional text (for example notification) add it to the message
        if self.additional_text:
            menu_text = self.additional_text + '\n\n' + menu_text

        # Add either start or end season action button
        latest_season_is_active = seasons and seasons[0].end_datetime is None
        end_or_start_button = end_season_btn if latest_season_is_active else start_season_btn

        text = dq_main_menu_text_body(menu_text)
        markup = InlineKeyboardMarkup([[info_btn, end_or_start_button, stats_btn]])
        await self.send_or_update_host_message(text, markup)

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        next_state: ActivityState | None = None
        match response_data:
            case info_btn.callback_data:
                next_state = DQInfoMessageState()
            case start_season_btn.callback_data:
                await self.activity.change_state(SetSeasonStartDateState())
            case end_season_btn.callback_data:
                await self.activity.change_state(SetLastQuestionWinnerState())
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
                case get_xlsx_btn.callback_data:
                    await send_bot_is_typing_status_update(self.activity.initial_update.effective_chat)
                    await send_dq_stats_excel_v2(self.get_chat_id(), self.current_season_id, context)
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


async def create_message_board_msg(message_board: MessageBoard, chat_id: int) -> MessageBoardMessage | None:
    """
    For creating daily question score table message as scheduled message.
    Enabled and created only if chat has active daily question season
    :param message_board:
    :param chat_id:
    :return:
    """
    target_datetime = datetime.utcnow()
    active_season: DailyQuestionSeason = database.find_active_dq_season(chat_id, target_datetime).first()
    if active_season:
        body = create_stats_for_season(active_season.id, include_choose_season_prompt=False)
        return MessageBoardMessage(message_board, body)


def create_stats_for_season(season_id: int, include_choose_season_prompt: bool = True):
    """
    Base logic. Each asked daily question means that the user won previous daily question
    (excluding first question of the season). This calculates how many question each
    user has asked and lists the scores in a sorted array. For the last question of the season,
    winner is determined by the answer marked as the winning answer of the last question.
    """
    season: DailyQuestionSeason = database.get_dq_season(season_id)

    answers_on_season: List[DailyQuestionAnswer] = list(database.find_answers_in_season(season.id))
    dq_on_season: List[DailyQuestion] = list(database.get_all_dq_on_season(season_id))
    users_on_chat: List[TelegramUser] = list(database.list_tg_users_for_chat(season.chat.id))

    # First make list of rows. Each row is single users data
    member_array = create_member_array(dq_on_season, answers_on_season, users_on_chat)
    # Add heading row
    member_array.insert(0, ['Nimi', 'V1', 'V2'])

    formatter = MessageArrayFormatter('| ', '<>').with_truncation(28, 0)
    formatted_members_array_str = formatter.format(member_array)

    footer = 'V1=Voitot, V2=Vastaukset'
    if include_choose_season_prompt:
        footer += '\nVoit valita toisen kauden tarkasteltavaksi alapuolelta.'

    msg_body = 'Päivän kysyjät \U0001F9D0\n\n' \
               + f'Kausi: {season.season_name}\n' \
               + f'Kausi alkanut: {fitzstr_from(season.start_datetime)}\n' \
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


class SetSeasonStartDateState(ActivityState):
    async def execute_state(self):
        heading = get_create_season_activity_heading(1, 3)
        reply_text = build_msg_text_body(heading, start_date_msg, create_season_started_by_dq(self))
        markup = InlineKeyboardMarkup(season_start_date_buttons())
        await self.send_or_update_host_message(reply_text, markup)

    async def preprocess_reply_data_hook(self, text: str) -> str | None:
        date = parse_dt_str_to_utctzstr(text)
        if has_no(date):
            heading = get_create_season_activity_heading(1, 3)
            reply_text = build_msg_text_body(heading, date_invalid_format_text)
            await self.send_or_update_host_message(reply_text)
        return date

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        if response_data == cancel_button.callback_data:
            # Return to the main menu with a notification
            await self.activity.change_state(DQMainMenuState(additional_text=start_season_cancelled))
            return
        utctd = datetime.fromisoformat(response_data)
        if utctd.date() == datetime.now().date():
            # If user has chosen today, use host message's datetime as it's more accurate
            utctd = self.activity.host_message.date
        # If given date overlaps is before previous session end date an error is given
        previous_season = database.find_dq_seasons_for_chat_order_id_desc(self.activity.get_chat_id()).first()
        if has(previous_season) \
                and utctd.date() < previous_season.end_datetime.date():  # utc
            error_message = get_start_date_overlaps_previous_season(previous_season.end_datetime)
            heading = get_create_season_activity_heading(1, 3)
            reply_text = build_msg_text_body(heading, error_message)
            await self.send_or_update_host_message(reply_text)
            return  # Input not valid. No state change

        await self.activity.change_state(SetSeasonNameState(utctd_season_start=utctd))


class SetSeasonNameState(ActivityState):
    def __init__(self, utctd_season_start):
        super().__init__()
        self.utctd_season_start = utctd_season_start

    async def execute_state(self):
        heading = get_create_season_activity_heading(2, 3)
        reply_text = build_msg_text_body(heading, season_name_msg)
        markup = InlineKeyboardMarkup(season_name_suggestion_buttons(self.get_chat_id()))
        await self.send_or_update_host_message(reply_text, markup)

    async def preprocess_reply_data_hook(self, text: str) -> str:
        if has(text) and len(text) <= 16:
            return text
        heading = get_create_season_activity_heading(2, 3)
        reply_text = build_msg_text_body(heading, season_name_too_long)
        await self.send_or_update_host_message(reply_text)

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        if response_data == cancel_button.callback_data:
            # Return to the main menu with a notification
            await self.activity.change_state(DQMainMenuState(additional_text=start_season_cancelled))
            return
        state = SeasonCreatedState(self.utctd_season_start, season_name=response_data)
        await self.activity.change_state(state)


class SeasonCreatedState(ActivityState):
    def __init__(self, utctd_season_start, season_name):
        super().__init__()
        self.utctd_season_start = utctd_season_start
        self.season_name = season_name

    async def execute_state(self):
        season = database.save_dq_season(chat_id=self.get_chat_id(),
                                         start_datetime=self.utctd_season_start,
                                         season_name=self.season_name)
        if create_season_started_by_dq(self):
            await database.save_daily_question(self.activity.initial_update, season)

        heading = get_create_season_activity_heading(3, 3)
        reply_text = build_msg_text_body(heading, get_season_created_msg, create_season_started_by_dq(self))
        await self.send_or_update_host_message(reply_text, InlineKeyboardMarkup([]))
        await self.activity.done()


def create_season_started_by_dq(state: ActivityState) -> bool:
    return has(state.activity.initial_update) and has(state.activity.initial_update.effective_message.text) \
        and '#päivänkysymys'.casefold() in state.activity.initial_update.effective_message.text.casefold()


def season_start_date_buttons():
    utc_today = dt_at_midday(datetime.now(utc))
    start_of_half_year = get_start_of_last_half_year(utc_today)
    start_of_quarter_year = get_start_of_last_quarter(utc_today)
    return [
        [
            cancel_button,
            InlineKeyboardButton(text=f'Tänään ({fitzstr_from(utc_today)})',
                                 callback_data=str(utc_today)),
        ],
        [
            InlineKeyboardButton(text=f'{fitzstr_from(start_of_quarter_year)}',
                                 callback_data=str(start_of_quarter_year)),
            InlineKeyboardButton(text=f'{fitzstr_from(start_of_half_year)}',
                                 callback_data=str(start_of_half_year))
        ]
    ]


def get_start_of_last_half_year(dt: datetime) -> datetime:
    if dt.month >= 7:
        return datetime(dt.year, 7, 1)
    return datetime(dt.year, 1, 1)


def get_start_of_last_quarter(d: datetime) -> datetime:
    full_quarter_count = int((d.month - 1) / 3)
    return datetime(d.year, int((full_quarter_count * 3) + 1), 1)


def season_name_suggestion_buttons(chat_id: int):
    buttons = []
    previous_seasons = database.find_dq_seasons_for_chat_order_id_desc(chat_id)

    prev_name_number_incremented_button = get_prev_season_name_with_incremented_number(previous_seasons)
    if has(prev_name_number_incremented_button):
        buttons.append(prev_name_number_incremented_button)

    season_by_year_button = get_this_years_season_number_button(previous_seasons)
    if has(season_by_year_button):
        buttons.append(season_by_year_button)

    buttons.append(get_full_emoji_button())
    buttons.append(get_full_emoji_button())

    emoji_str_1 = "".join(get_random_number_of_emoji(1, 3))
    emoji_str_2 = "".join(get_random_number_of_emoji(1, 3))
    name_with_emoji_1 = f'{emoji_str_1} {datetime.now(fitz).year} {emoji_str_2}'
    name_with_emoji_2 = f'Kausi {"".join(get_random_number_of_emoji(1, 3))}'
    name_with_emoji_3 = f'Kysymyskausi {"".join(get_random_number_of_emoji(1, 3))}'

    buttons.append(InlineKeyboardButton(text=name_with_emoji_1, callback_data=name_with_emoji_1))
    buttons.append(InlineKeyboardButton(text=name_with_emoji_2, callback_data=name_with_emoji_2))
    buttons.append(InlineKeyboardButton(text=name_with_emoji_3, callback_data=name_with_emoji_3))

    random.shuffle(buttons)  # NOSONAR
    buttons = [cancel_button] + buttons
    return split_to_chunks(buttons, 2)


def get_prev_season_name_with_incremented_number(previous_seasons: QuerySet):
    if has(previous_seasons):
        digit_match = re.search(r'\d+', previous_seasons.first().season_name)
        if has(digit_match) and has(digit_match.group()):  # name has eny digit
            prev_number = int(digit_match.group(0))
            new_season_name = previous_seasons.first().season_name.replace(str(prev_number), str(prev_number + 1), 1)
            return InlineKeyboardButton(text=new_season_name, callback_data=new_season_name)


def get_full_emoji_button():
    emoji_string = ''.join(get_random_number_of_emoji(2, 5))
    return InlineKeyboardButton(text=emoji_string, callback_data=emoji_string)


def get_this_years_season_number_button(previous_seasons: QuerySet):
    year = datetime.now(fitz).year
    star_of_year = datetime.now(fitz).replace(year, 1, 1)
    season_number = 1
    seasons_this_year = previous_seasons.filter(start_datetime__gte=star_of_year)
    if has(seasons_this_year):
        season_number = seasons_this_year.count() + 1
    name = f'Kausi {season_number}/{year}'
    return InlineKeyboardButton(text=name, callback_data=name)


def get_create_season_activity_heading(step_number: int, number_of_steps: int):
    return f'[Luo uusi kysymyskausi ({step_number}/{number_of_steps})]'


def get_message_body(started_by_dq: bool):
    if started_by_dq:
        return 'Ryhmässä ei ole aktiivista kautta päivän kysymyksille. Jotta kysymyksiä voidaan ' \
               'tilastoida, tulee ensin luoda uusi kysymyskausi.\n------------------\n'
    else:
        return ''


start_season_cancelled = 'Kysymyskauden aloittaminen peruutettu.'
start_date_msg = 'Valitse ensin kysymyskauden aloituspäivämäärä alta tai anna se vastaamalla tähän viestiin.'
season_name_msg = 'Valitse vielä kysymyskauden nimi tai anna se vastaamalla tähän viestiin.'
season_name_too_long = 'Kysymyskauden nimi voi olla enintään 16 merkkiä pitkä'


def get_start_date_overlaps_previous_season(prev_s_end_date):
    return f'Uusi kausi voidaan merkitä alkamaan aikaisintaan edellisen kauden päättymispäivänä. ' \
           f'Edellinen kausi on merkattu päättyneeksi {fitzstr_from(prev_s_end_date)}'


def get_season_created_msg(started_by_dq: bool):
    if started_by_dq:
        return 'Uusi kausi aloitettu ja aiemmin lähetetty päivän kysymys tallennettu linkitettynä juuri luotuun kauteen'
    else:
        return 'Uusi kausi aloitettu, nyt voit aloittaa päivän kysymysten esittämisen. Viesti tunnistetaan ' \
               'automaattisesti päivän kysymykseksi, jos se sisältää tägin \'#päivänkysymys\'.'


def build_msg_text_body(heading: str, state_message_provider, started_by_dq: bool = False):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider(started_by_dq=started_by_dq)
    return f'{heading}\n' \
           f'------------------\n' \
           f'{get_message_body(started_by_dq)}' \
           f'{state_msg}'


class SetLastQuestionWinnerState(ActivityState):
    _default_prompt = 'Valitse ensin edellisen päivän kysymyksen ({}) voittaja alta. Näytetään sivu {}/{}.'
    _users_per_page = 6

    _previous_button = InlineKeyboardButton(text='Edellinen sivu', callback_data='/previous_page')
    _next_button = InlineKeyboardButton(text='Seuraava sivu', callback_data='/next_page')

    def __init__(self, activity: 'CommandActivity' = None):
        super().__init__(activity)
        self.chat_id: Optional[int] = None
        self.last_dq_date_of_question: Optional[datetime] = None
        self.chats_users: List[TelegramUser] = []
        self.current_page: int = 0

    async def execute_state(self):
        self.chat_id = self.get_chat_id()
        target_datetime = self.activity.host_message.date  # utc
        season = database.find_active_dq_season(self.chat_id, target_datetime).first()
        last_dq = database.get_all_dq_on_season(season.id).last()

        # If season has no questions it is just removed straight away
        if not last_dq:
            await self.remove_season_without_dq(season)
            return

        self.last_dq_date_of_question = last_dq.date_of_question
        await self.update_user_listing()

    async def update_user_listing(self):
        # Has questions -> ask user to choose last questions winner
        self.chats_users = (database.list_tg_users_for_chat(self.chat_id)
                            .order_by('username', 'first_name', 'last_name'))

        total_number_of_pages = math.ceil(len(self.chats_users) / self._users_per_page)
        reply_text = self._default_prompt.format(
            fitzstr_from(self.last_dq_date_of_question),
            self.current_page + 1,
            total_number_of_pages)

        heading = get_stop_season_activity_heading(1, 3)
        reply = build_msg_text_body(heading, reply_text)

        markup = InlineKeyboardMarkup([self.create_first_row_buttons(), *self.create_user_buttons()])
        await self.send_or_update_host_message(reply, markup)

    def create_first_row_buttons(self) -> List[InlineKeyboardButton]:
        buttons = [cancel_button]
        if self.current_page > 0:
            buttons.append(self._previous_button)
        if (self.current_page + 1) * self._users_per_page < len(self.chats_users):
            buttons.append(self._next_button)
        return buttons

    def create_user_buttons(self) -> List[InlineKeyboardButton]:
        offset = self.current_page * self._users_per_page
        users_to_show = self.chats_users[offset:offset + self._users_per_page]
        buttons = [InlineKeyboardButton(text=str(user), callback_data=user.id) for user in users_to_show]
        return split_to_chunks(buttons, 3)

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        if update.callback_query:
            data = update.callback_query.data
            match data:
                case cancel_button.callback_data:
                    await self.activity.change_state(DQMainMenuState(additional_text=end_season_cancelled))
                case self._previous_button.callback_data:
                    self.current_page -= 1
                    await self.update_user_listing()
                case self._next_button.callback_data:
                    self.current_page += 1
                    await self.update_user_listing()
                case _:  # User button is pressed
                    user_id = data
                    await self.activity.change_state(SetSeasonEndDateState(user_id))

    async def remove_season_without_dq(self, season: DailyQuestionSeason):
        season.delete()
        heading = get_stop_season_activity_heading(1, 1)
        reply_test = build_msg_text_body(heading, no_dq_season_deleted_msg)
        await self.send_or_update_host_message(reply_test)
        await self.activity.done()


class SetSeasonEndDateState(ActivityState):
    def __init__(self, last_win_user_id=None):
        super().__init__()
        self.last_win_user_id = last_win_user_id
        self.season = None
        self.last_dq = None

    async def execute_state(self):
        chat_id = self.get_chat_id()
        self.season: DailyQuestionSeason = database.find_active_dq_season(chat_id, self.activity.host_message.date).first()  # utc
        self.last_dq: DailyQuestion = database.get_all_dq_on_season(self.season.id).last()

        heading = get_stop_season_activity_heading(2, 3)
        selected_last_question_winner = database.get_telegram_user(self.last_win_user_id)

        reply_text = build_msg_text_body(heading, end_date_msg.format(str(selected_last_question_winner)))
        markup = InlineKeyboardMarkup(season_end_date_buttons(self.last_dq.date_of_question))
        await self.send_or_update_host_message(reply_text, markup)

    async def preprocess_reply_data_hook(self, text: str) -> str | None:
        date = parse_dt_str_to_utctzstr(text)
        if has_no(date):
            heading = get_stop_season_activity_heading(2, 3)
            reply_text = build_msg_text_body(heading, date_invalid_format_text)
            await self.send_or_update_host_message(reply_text)
        return date

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        if response_data == cancel_button.callback_data:
            await self.activity.change_state(DQMainMenuState(additional_text=end_season_cancelled))
            return
        utctd = datetime.fromisoformat(response_data)
        if utctd.date() == datetime.now().date():
            # If user has chosen today, use host message's datetime as it's more accurate
            utctd = self.activity.host_message.date

        # Check that end date is at same or after last dq date
        if utctd.date() < self.last_dq.date_of_question.date():  # utc
            heading = get_stop_season_activity_heading(2, 3)
            reply_text = build_msg_text_body(heading, get_end_date_must_be_same_or_after_last_dq(self.last_dq.date_of_question))
            await self.send_or_update_host_message(reply_text)
            return  # Inform user that date has to be same or after last dq's date of question

        # Update Season to have end date
        self.season.end_datetime = utctd
        self.season.save()

        # Either update users answer on the last dq to be winning answer
        # OR if user has no answer saved, create new "empty" winning answer
        answer = database.find_answer_by_user_to_dq(self.last_dq.id, self.last_win_user_id).first()
        if answer:
            answer.is_winning_answer = True
            answer.save()
        else:
            database.save_dq_answer_without_message(daily_question=self.last_dq,
                                                    author_id=self.last_win_user_id,
                                                    is_winning_answer=True)

        await self.activity.change_state(SeasonEndedState(utctd))


class SeasonEndedState(ActivityState):
    def __init__(self, utctztd_end):
        super().__init__()
        self.utctztd_end = utctztd_end

    async def execute_state(self):
        heading = get_stop_season_activity_heading(3, 3)
        reply_text = build_msg_text_body(heading, lambda *args, **kwargs: get_season_ended_msg(self.utctztd_end))
        await self.send_or_update_host_message(reply_text, InlineKeyboardMarkup([]))
        await self.activity.done()


def season_end_date_buttons(last_dq_dt: datetime):
    utc_now = datetime.now(utc)
    # Edge case, where user has asked next days question and then decides to end season for some reason
    if has(last_dq_dt) and last_dq_dt > utc_now:
        end_date_button = InlineKeyboardButton(text=f'{fi_short_day_name(fitz_from(utc_now))} {fitzstr_from(last_dq_dt)}',
                                               callback_data=str(last_dq_dt))
    else:
        end_date_button = InlineKeyboardButton(text=f'Tänään ({fitzstr_from(utc_now)})',
                                               callback_data=str(utc_now))
    return [[cancel_button, end_date_button]]


def get_stop_season_activity_heading(step_number: int, number_of_steps: int):
    return f'[Lopeta kysymysausi ({step_number}/{number_of_steps})]'


end_date_msg = ('Viimeisen kysymyksen voittajaksi valittu {}.\n'
                'Valitse kysymyskauden päättymispäivä alta tai anna se vastaamalla tähän viestiin.')


def get_end_date_must_be_same_or_after_last_dq(last_dq_date_of_question: datetime):
    return f'Kysymyskausi voidaan merkitä päättyneeksi aikaisintaan viimeisen esitetyn päivän kysymyksen päivänä. ' \
           f'Viimeisin kysymys esitetty {fitzstr_from(last_dq_date_of_question)}.'


end_season_cancelled = 'Kysymyskauden päättäminen peruutettu.'
no_dq_season_deleted_msg = 'Ei esitettyjä kysymyksiä kauden aikana, joten kausi poistettu kokonaan.'


def get_season_ended_msg(utctztd_end: datetime):
    date_str = 'tänään' if datetime.now(utc).date() == utctztd_end.date() else fitzstr_from(utctztd_end)
    return f'Kysymyskausi merkitty päättyneeksi {date_str}. Voit aloittaa uuden kauden kysymys-valikon kautta.'



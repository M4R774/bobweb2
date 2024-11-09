import random
import re
from datetime import datetime

from django.db.models import QuerySet
from pytz import utc
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState, cancel_button
from bobweb.bob.activities.command_activity import date_invalid_format_text, parse_dt_str_to_utctzstr
from bobweb.bob.resources.unicode_emoji import get_random_number_of_emoji
from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.utils_common import has, split_to_chunks, has_no, fitzstr_from, dt_at_midday


class SetSeasonStartDateState(ActivityState):
    async def execute_state(self):
        reply_text = build_msg_text_body(1, 3, start_date_msg, started_by_dq(self))
        markup = InlineKeyboardMarkup(season_start_date_buttons())
        await self.send_or_update_host_message(reply_text, markup)

    async def preprocess_reply_data_hook(self, text: str) -> str | None:
        date = parse_dt_str_to_utctzstr(text)
        if has_no(date):
            reply_text = build_msg_text_body(1, 3, date_invalid_format_text)
            await self.send_or_update_host_message(reply_text)
        return date

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        if response_data == cancel_button.callback_data:
            await self.send_or_update_host_message(start_season_cancelled)
            await self.activity.done()
            return
        utctd = datetime.fromisoformat(response_data)
        if utctd.date() == datetime.now().date():
            # If user has chosen today, use host message's datetime as it's more accurate
            utctd = self.activity.host_message.date
        # If given date overlaps is before previous session end date an error is given
        previous_season = database.find_dq_seasons_for_chat(self.activity.get_chat_id()).first()
        if has(previous_season) \
                and utctd.date() < previous_season.end_datetime.date():  # utc
            error_message = get_start_date_overlaps_previous_season(previous_season.end_datetime)
            reply_text = build_msg_text_body(1, 3, error_message)
            await self.send_or_update_host_message(reply_text)
            return  # Input not valid. No state change

        await self.activity.change_state(SetSeasonNameState(utctd_season_start=utctd))


class SetSeasonNameState(ActivityState):
    def __init__(self, utctd_season_start):
        super().__init__()
        self.utctd_season_start = utctd_season_start

    async def execute_state(self):
        reply_text = build_msg_text_body(2, 3, season_name_msg)
        markup = InlineKeyboardMarkup(season_name_suggestion_buttons(self.get_chat_id()))
        await self.send_or_update_host_message(reply_text, markup)

    async def preprocess_reply_data_hook(self, text: str) -> str:
        if has(text) and len(text) <= 16:
            return text
        reply_text = build_msg_text_body(2, 3, season_name_too_long)
        await self.send_or_update_host_message(reply_text)

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        if response_data == cancel_button.callback_data:
            await self.send_or_update_host_message(start_season_cancelled)
            await self.activity.done()
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
        if started_by_dq(self):
            await database.save_daily_question(self.activity.initial_update, season)

        reply_text = build_msg_text_body(3, 3, get_season_created_msg, started_by_dq(self))
        await self.send_or_update_host_message(reply_text, InlineKeyboardMarkup([]))
        await self.activity.done()


def started_by_dq(state: ActivityState) -> bool:
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
    previous_seasons = database.find_dq_seasons_for_chat(chat_id)

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

    random.shuffle(buttons)
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


def get_activity_heading(step_number: int, number_of_steps: int):
    return f'[Luo uusi kysymyskausi ({step_number}/{number_of_steps})]'


def get_message_body(started_by_dq: bool):
    if started_by_dq:
        return 'Ryhmässä ei ole aktiivista kautta päivän kysymyksille. Jotta kysymyksiä voidaan ' \
               'tilastoida, tulee ensin luoda uusi kysymyskausi.\n------------------\n'
    else:
        return ''


start_season_cancelled = 'Selvä homma, kysymyskauden aloittaminen peruutettu.'
start_date_msg = f'Valitse ensin kysymyskauden aloituspäivämäärä alta tai anna se vastaamalla tähän viestiin.'
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


def build_msg_text_body(i: int, n: int, state_message_provider, started_by_dq: bool = False):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider(started_by_dq=started_by_dq)
    return f'{get_activity_heading(i, n)}\n' \
           f'------------------\n' \
           f'{get_message_body(started_by_dq)}' \
           f'{state_msg}'

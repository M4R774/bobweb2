import random
import re
from datetime import datetime

from django.db.models import QuerySet
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.activity_utils import parse_date
from bobweb.bob.activities.daily_question.start_season_activity import StartSeasonActivity
from bobweb.bob.activities.daily_question.unicode_emoji import get_random_number_of_emoji
from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT
from bobweb.bob.utils_common import has, split_to_chunks, has_no


# Common class for all states related to StartSeasonActivity
class StartSeasonActivityState(ActivityState):
    def __init__(self, activity: StartSeasonActivity = None):
        super().__init__()
        self.activity = activity

    def started_by_dq(self) -> bool:
        return has(self.activity.update_with_dq)

    def reply_or_update_message(self, reply_text: str, markup: InlineKeyboardMarkup):
        # If triggered by user's daily_question message there is not host message to yet update.
        # In that case new message is sent by the bot and that message is set as host_message.
        # Otherwise, update host message content
        if self.started_by_dq() and self.activity.host_message is None:
            response = self.activity.update_with_dq.effective_message.reply_text(reply_text, reply_markup=markup)
            self.activity.host_message = response
        else:
            self.activity.update_host_message_content(reply_text, markup)


class SetSeasonStartDateState(StartSeasonActivityState):
    def execute_state(self):
        chat_id = self.activity.get_chat_id()
        self.activity.previous_season = database.find_dq_seasons_for_chat(chat_id).first()

        reply_text = build_msg_text_body(1, 3, start_date_msg, self.started_by_dq())
        markup = InlineKeyboardMarkup(season_start_date_buttons())
        self.reply_or_update_message(reply_text, markup)

    def preprocess_reply_data(self, text: str) -> str | None:
        date = parse_date(text)
        if has_no(date):
            reply_text = build_msg_text_body(1, 3, start_date_invalid_format)
            self.activity.update_host_message_content(reply_text)
        return date

    def handle_response(self, response_data: str):
        date_time_obj = datetime.fromisoformat(response_data)
        # If given date overlaps is before previous session end date an error is given
        if has(self.activity.previous_season) \
                and date_time_obj.date() < self.activity.previous_season.end_datetime.date():
            error_message = get_start_date_overlaps_previous_season(self.activity.previous_season.end_datetime)
            reply_text = build_msg_text_body(1, 3, error_message)
            self.activity.update_host_message_content(reply_text)
            return  # Input not valid. No state change

        self.activity.season_start_date_input = date_time_obj
        self.activity.change_state(SetSeasonNameState())


class SetSeasonNameState(StartSeasonActivityState):
    def execute_state(self):
        reply_text = build_msg_text_body(2, 3, season_name_msg)
        markup = InlineKeyboardMarkup(season_name_suggestion_buttons(self.activity.host_message.chat_id))
        self.activity.update_host_message_content(reply_text, markup)

    def preprocess_reply_data(self, text: str) -> str:
        if has(text) and len(text) <= 16:
            return text
        reply_text = build_msg_text_body(2, 3, season_name_too_long)
        self.activity.update_host_message_content(reply_text)

    def handle_response(self, response_data: str):
        self.activity.season_name_input = response_data
        self.activity.change_state(SeasonCreatedState())


class SeasonCreatedState(StartSeasonActivityState):
    def execute_state(self):
        season = database.save_dq_season(chat_id=self.activity.host_message.chat_id,
                                         start_datetime=self.activity.season_start_date_input,
                                         season_name=self.activity.season_name_input)
        if self.started_by_dq():
            database.save_daily_question(self.activity.update_with_dq, season)

        reply_text = build_msg_text_body(3, 3, get_season_created_msg, self.started_by_dq())
        self.activity.update_host_message_content(reply_text, InlineKeyboardMarkup([[]]))
        self.activity.done()


def season_start_date_buttons():
    now = datetime.today()
    today = datetime(now.year, now.month, now.day)
    start_of_half_year = get_start_of_last_half_year(today)
    start_of_quarter_year = get_start_of_last_quarter(today)
    return [
        [
            InlineKeyboardButton(text=f'Tänään ({today.strftime(FINNISH_DATE_FORMAT)})',
                                 callback_data=str(today)),
        ],
        [
            InlineKeyboardButton(text=f'{start_of_quarter_year.strftime(FINNISH_DATE_FORMAT)}',
                                 callback_data=str(start_of_quarter_year)),
            InlineKeyboardButton(text=f'{start_of_half_year.strftime(FINNISH_DATE_FORMAT)}',
                                 callback_data=str(start_of_half_year))
        ]
    ]


def get_start_of_last_half_year(date_of_context: datetime) -> datetime:
    if date_of_context.month > 7:
        return datetime(date_of_context.year, 7, 1)
    return datetime(date_of_context.year, 1, 1)


def get_start_of_last_quarter(date_of_context: datetime) -> datetime:
    number_of_full_quarters = int((date_of_context.month - 1) / 3)
    return datetime(date_of_context.year, int((number_of_full_quarters * 3) + 1), 1)


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
    name_with_emoji_1 = f'{emoji_str_1} {datetime.today().year} {emoji_str_2}'
    name_with_emoji_2 = f'Kausi {"".join(get_random_number_of_emoji(1, 3))}'
    name_with_emoji_3 = f'Kysymyskausi {"".join(get_random_number_of_emoji(1, 3))}'

    buttons.append(InlineKeyboardButton(text=name_with_emoji_1, callback_data=name_with_emoji_1))
    buttons.append(InlineKeyboardButton(text=name_with_emoji_2, callback_data=name_with_emoji_2))
    buttons.append(InlineKeyboardButton(text=name_with_emoji_3, callback_data=name_with_emoji_3))

    random.shuffle(buttons)
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
    today = datetime.today()
    star_of_year = datetime.fromisoformat(f'{today.year}-01-01')
    season_number = 1
    seasons_this_year = previous_seasons.filter(start_datetime__gte=star_of_year)
    if has(seasons_this_year):
        season_number = seasons_this_year.count() + 1
    name = f'Kausi {season_number}/{today.year}'
    return InlineKeyboardButton(text=name, callback_data=name)


def get_activity_heading(step_number: int, number_of_steps: int):
    return f'[Luo uusi kysymyskausi ({step_number}/{number_of_steps})]'


def get_message_body(started_by_dq: bool):
    if started_by_dq:
        return 'Ryhmässä ei ole aktiivista kautta päivän kysymyksille. Jotta kysymyksiä voidaan ' \
               'tilastoida, tulee ensin luoda uusi kysymyskausi.\n------------------\n'
    else:
        return ''


start_date_msg = f'Valitse ensin kysymyskauden aloituspäivämäärä alta tai anna se vastaamalla tähän viestiin.'
start_date_formats = 'Tuetut formaatit ovat \'vvvv-kk-pp\', \'pp.kk.vvvv\' ja \'kk/pp/vvvv\'.'
start_date_invalid_format = f'Antamasi päivämäärä ei ole tuettua muotoa. {start_date_formats}'

season_name_msg = 'Valitse vielä kysymyskauden nimi tai anna se vastaamalla tähän viestiin.'
season_name_too_long = 'Kysymyskauden nimi voi olla enintään 16 merkkiä pitkä'


def get_start_date_overlaps_previous_season(prev_s_end_date):
    return f'Uusi kausi voidaan merkitä alkamaan aikaisintaan edellisen kauden päättymispäivänä. ' \
           f'Edellinen kausi on merkattu päättyneeksi {prev_s_end_date.strftime(FINNISH_DATE_FORMAT)}'


def get_season_created_msg(started_by_dq: bool):
    if started_by_dq:
        return 'Uusi kausi aloitettu ja aiemmin lähetetty päivän kysymys tallennettu linkitettynä juuri luotuun kauteen'
    else:
        return 'Uusi kausi aloitettu, nyt voit aloittaa päivän kysymysten esittämisen. Viesti tunnistetaan ' \
               'automaattisesti päivän kysymykseksi, jos se sisältää tägäyksen \'#päivänkysymys\'.'


def build_msg_text_body(i: int, n: int, state_message_provider, started_by_dq: bool = False):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider(started_by_dq=started_by_dq)
    return f'{get_activity_heading(i, n)}\n' \
           f'------------------\n' \
           f'{get_message_body(started_by_dq)}' \
           f'{state_msg}'

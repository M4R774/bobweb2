from datetime import datetime, date

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Message
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.resources.bob_constants import ISO_DATE_FORMAT, FINNISH_DATE_FORMAT
from bobweb.bob.utils_common import has


# Activity for creating a new daily question season. Can be initiated by DailyQuestion command
# or by a message with '#päivänkysymys' when no season is active
class CreateSeasonActivity(CommandActivity):
    def __init__(self,
                 host_message: Message = None,
                 activity_state: ActivityState = None,
                 update_with_dq: Update = None):
        super().__init__(host_message, activity_state)
        self.season_number_input = None
        self.season_start_date_input = None
        self.update_with_dq = update_with_dq


# Common class for all states related to CreateSeasonActivity
class CreateSeasonActivityState(ActivityState):
    def __init__(self, activity: CreateSeasonActivity):
        super().__init__()
        self.activity = activity

    def started_by_dq(self) -> bool:
        return self.activity.update_with_dq is not None

    # For create season activity no real difference between handle_callback and handle_update so they might aswell
    # be handeled by same method
    def handle_callback(self, update: Update, context: CallbackContext):
        self.handle_reply(update, context)


class SetSeasonStartDateState(CreateSeasonActivityState):
    def __init__(self, activity: CreateSeasonActivity, initial_update):
        super().__init__(activity)
        self.initial_update = initial_update

    def execute_state(self):
        reply_text = build_msg_text_body(1, 3, self.started_by_dq(), start_date_msg)
        markup = InlineKeyboardMarkup(create_season_start_date_buttons())
        self.activity.host_message = self.initial_update.message.reply_text(reply_text, reply_markup=markup)

    def handle_reply(self, update: Update, context: CallbackContext = None):
        date_string = update.callback_query.data
        try:
            date_time_obj = datetime.fromisoformat(date_string)
            self.activity.season_start_date_input = date_time_obj

            next_state = SetSeasonNumberState(activity=self.activity)
            self.activity.change_state(next_state)
        except ValueError:
            print('value error')


def create_season_start_date_buttons():
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


class SetSeasonNumberState(CreateSeasonActivityState):
    def __init__(self, activity: CreateSeasonActivity):
        super().__init__(activity)

    def execute_state(self):
        reply_text = build_msg_text_body(2, 3, self.started_by_dq(), season_number_msg)
        markup = InlineKeyboardMarkup(create_season_number_buttons(self.activity.host_message.chat_id))
        self.activity.update_host_message_content(reply_text, markup)

    def handle_reply(self, update: Update, context: CallbackContext = None):
        season_number = int(update.callback_query.data)
        self.activity.season_number_input = season_number

        next_state = SeasonCreatedState(self.activity)
        self.activity.change_state(next_state)


def create_season_number_buttons(chat_id: int):
    previous_season_number_in_chat = database.find_dq_seasons_for_chat(chat_id)
    next_season_number = 1
    if has(previous_season_number_in_chat):
        next_season_number = previous_season_number_in_chat.first().season_number + 1
    return [[
        InlineKeyboardButton(text=f'{next_season_number}', callback_data=str(next_season_number))
    ]]


class SeasonCreatedState(CreateSeasonActivityState):
    def __init__(self, activity: CreateSeasonActivity):
        super().__init__(activity)

    def execute_state(self):
        season = database.save_dq_season(chat_id=self.activity.host_message.chat_id,
                                         start_datetime=self.activity.season_start_date_input,
                                         season_number=self.activity.season_number_input)
        database.save_daily_question(self.activity.update_with_dq, season)

        reply_text = build_msg_text_body(3, 3, self.started_by_dq(), get_season_created_msg)
        self.activity.update_host_message_content(reply_text)


def get_activity_heading(step_number: int, number_of_steps: int):
    return f'[Luo uusi kysymyskausi ({step_number}/{number_of_steps})]'


def get_message_body(started_by_dq: bool):
    if started_by_dq:
        return 'Ryhmässä ei ole aktiivista kautta päivän kysymyksille. Jotta kysymyksiä voidaan ' \
               'tilastoida, tulee ensin luoda uusi kysymyskausi.\n'
    else:
        return 'Luo uusi päivän kysymyksen kausi.'


start_date_msg = f'Valitse ensin kysymyskauden aloituspäivämäärä alta tai anna se vastaamalla tähän viestiin.'
start_date_formats = 'Tuetut formaatit ovat \'vvvv-kk-pp\' ja \'pp.kk.vvvv\'.'
start_date_invalid_format = f'Antamasi päivämäärä ei ole tuettua muotoa. {start_date_formats}'

season_number_msg = 'Valitse vielä kysymyskauden numero tai anna se vastaamalla tähän viestiin.'
season_number_invalid_format = 'Kysymyskauden numeron tulee olla kokonaisluku.'


def get_season_created_msg(started_by_dq: bool):
    if started_by_dq:
        return 'Uusi kausi luotu ja aiemmin lähetetty päivän kysymys tallennettu linkitettynä juuri luotuun kauteen'
    else:
        return 'Uusi kausi luotu, nyt voit aloittaa päivän kysymysten esittämisen. Viesti tunnistetaan ' \
               'automaattisesti päivän kysymykseksi, jos se sisältää tägäyksen \'#päivänkysymys\'.'


def build_msg_text_body(i: int, n: int, started_by_dq: bool, state_message_provider):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider(started_by_dq=started_by_dq)
    return f'{get_activity_heading(i, n)}\n' \
           f'------------------\n' \
           f'{get_message_body(started_by_dq)}\n' \
           f'------------------\n' \
           f'{state_msg}'
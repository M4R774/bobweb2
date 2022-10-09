from datetime import datetime, date

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity


class CreateSeasonActivity(CommandActivity):
    def __init__(self, host_update: Update, activity_state: ActivityState = None):
        # if activity_state is None:
        #     activity_state = SetSeasonStartDateState()
        super().__init__(host_update, activity_state)
        self.season_number_input = None
        self.season_start_date_input = None


create_season_activity_heading = '`[Luo uusi kysymyskausi]`'
no_season_heading_description = 'Ryhmässä ei ole aktiivista kautta päivän kysymyksille. Jotta kysymyksiä voidaan ' \
                                'tilastoida, tulee ensin luoda uusi kysymyskausi.\n\n'

start_date_formats = 'Tuetut formaatit ovat \'vvvv-kk-pp\' ja \'pp.kk.vvvv\'.'
start_date_msg = f'Valitse ensin kysymyskauden aloituspäivämäärä alta tai anna se vastaamalla tähän ' \
                 f'viestiin. {start_date_formats}'
start_date_invalid_format = f'Antamasi päivämäärä ei ole tuettua muotoa. {start_date_formats}'


class SetSeasonStartDateState(ActivityState):

    def update_message(self, host_update: Update):
        reply_text = f'{create_season_activity_heading}\n{no_season_heading_description}'
        markup = InlineKeyboardMarkup(create_season_start_date_buttons())
        host_update.message.reply_text(reply_text, reply_markup=markup)

    def handle_callback(self, update: Update, context: CallbackContext = None):

        date_string = update.callback_query
        print(date_string)
        # käyttäjä klikkaa jotain annettua nappia
        # -> lisää päivämäärä ja siirrä seuraavaan stateen

    def handle_reply(self, update: Update, context: CallbackContext = None):
        # käyttäjä lähettä päivämäärän viestillä
        # - jos ei validi: ilmoita käyttäjälle ja jää tähän stateen
        # - jos validi: lisää päivämäärä ja siirrä seuraavaan stateen
        date_string = update.message
        print(date_string)


def create_season_start_date_buttons():
    today = datetime.today().date()
    start_of_half_year = get_start_of_last_half_year(today)
    start_of_quarter_year = get_start_of_last_quarter(today)
    return [
        [
            InlineKeyboardButton(text=f'Tänään ({today})',
                                 callback_data=str(today)),
            InlineKeyboardButton(text=f'{start_of_quarter_year}',
                                 callback_data=str(start_of_quarter_year)),
            InlineKeyboardButton(text=f'{start_of_half_year}',
                                 callback_data=str(start_of_half_year))
        ]
    ]


def get_start_of_last_half_year(date_of_context: date) -> date:
    if date_of_context.month < 7:
        return date(date_of_context.year, 7, 1)
    return date(date_of_context.year, 1, 1)


def get_start_of_last_quarter(date_of_context: date) -> date:
    number_of_full_quarters = int((date_of_context.month - 1) / 3)
    return date(date_of_context.year, int((number_of_full_quarters * 3) + 1), 1)

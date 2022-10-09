from datetime import datetime, date

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Message
from telegram.ext import CallbackContext

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.resources.bob_constants import ISO_DATE_FORMAT, FINNISH_DATE_FORMAT

create_season_activity_heading = '`[Luo uusi kysymyskausi]`'
no_season_heading_description = 'Ryhmässä ei ole aktiivista kautta päivän kysymyksille. Jotta kysymyksiä voidaan ' \
                                'tilastoida, tulee ensin luoda uusi kysymyskausi.\n\n'

start_date_formats = 'Tuetut formaatit ovat \'vvvv-kk-pp\' ja \'pp.kk.vvvv\'.'
start_date_msg = f'Valitse ensin kysymyskauden aloituspäivämäärä alta tai anna se vastaamalla tähän ' \
                 f'viestiin. {start_date_formats}'
start_date_invalid_format = f'Antamasi päivämäärä ei ole tuettua muotoa. {start_date_formats}'


class CreateSeasonActivity(CommandActivity):
    def __init__(self, host_message: Message = None, activity_state: ActivityState = None):
        super().__init__(host_message, activity_state)
        self.season_number_input = None
        self.season_start_date_input = None

class SetSeasonStartDateState(ActivityState):
    def __init__(self, activity, initial_update):
        super().__init__(activity)
        self.initial_update = initial_update

    def update_message(self, host_message: Message):
        reply_text = f'{create_season_activity_heading}\n{no_season_heading_description}\n\n{start_date_msg}'
        markup = InlineKeyboardMarkup(create_season_start_date_buttons())
        response = self.initial_update.message.reply_text(reply_text, reply_markup=markup)
        self.activity.host_message = response
        print(response.message_id)

    def handle_callback(self, update: Update, context: CallbackContext = None):
        date_string = update.callback_query.data
        try:
            # käyttäjä klikkaa jotain annettua nappia
            # -> lisää päivämäärä ja siirrä seuraavaan stateen
            date_time_obj = datetime.strptime(date_string, ISO_DATE_FORMAT)

        except ValueError:
            print('value error')


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


def get_start_of_last_half_year(date_of_context: date) -> date:
    if date_of_context.month > 7:
        return date(date_of_context.year, 7, 1)
    return date(date_of_context.year, 1, 1)


def get_start_of_last_quarter(date_of_context: date) -> date:
    number_of_full_quarters = int((date_of_context.month - 1) / 3)
    return date(date_of_context.year, int((number_of_full_quarters * 3) + 1), 1)

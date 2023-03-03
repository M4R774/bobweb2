import datetime
import logging

from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob import command_service
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.activity_state import ActivityState, back_button
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.nordpool_service import DayData, get_data_for_date, get_vat_str, get_vat_by_date, \
    cache_has_data_for_tomorrow
from bobweb.bob.resources.bob_constants import fitz

logger = logging.getLogger(__name__)


class SahkoCommand(ChatCommand):
    run_async = True  # Should be asynchronous

    def __init__(self):
        super().__init__(
            name='sahko',
            regex=regex_simple_command('sähkö'),
            help_text_short=('!sahko', 'Sähkön hinta')
        )

    def is_enabled_in(self, chat):
        return True

    def handle_update(self, update: Update, context: CallbackContext = None):
        activity = CommandActivity(initial_update=update, state=SahkoBaseState())
        command_service.instance.add_activity(activity)


# Buttons for SahkoBaseState
show_graph_btn = InlineKeyboardButton(text='Näytä 📊', callback_data='/show_graph')
hide_graph_btn = InlineKeyboardButton(text='Piilota 📊', callback_data='/hide_graph')
show_tomorrow_btn = InlineKeyboardButton(text='Huominen ⏩', callback_data='/show_tomorrow')
show_today_btn = InlineKeyboardButton(text='Tänään ⏪', callback_data='/show_today')
info_btn = InlineKeyboardButton(text='Info ⁉', callback_data='/show_info')

fetch_failed_msg = 'Sähkön hintojen haku epäonnistui 🔌✂️'


class SahkoBaseState(ActivityState):
    def __init__(self, show_graph: bool = False, target_date: datetime.date = None):
        super().__init__()
        self.show_graph = show_graph
        self.target_date = target_date

    def execute_state(self):
        today = datetime.datetime.now(tz=fitz).date()
        if self.target_date is None or self.target_date < today:
            self.target_date = today
        try:
            data: DayData = get_data_for_date(target_date=self.target_date)
            if data is None:
                raise Exception
        except Exception as e:
            logger.error(e)
            self.activity.reply_or_update_host_message(fetch_failed_msg, markup=InlineKeyboardMarkup([[]]))
            return

        description = f'Hinnat yksikössä snt/kWh (sis. ALV {get_vat_str(get_vat_by_date(self.target_date))}%)'

        if self.show_graph:
            reply_text = f'{data.data_array}{data.data_graph}{description}'
            buttons = [hide_graph_btn, info_btn]
        else:
            reply_text = f'{data.data_array}{description}'
            buttons = [show_graph_btn, info_btn]

        if cache_has_data_for_tomorrow() and self.target_date == today:
            buttons.append(show_tomorrow_btn)
        elif self.target_date != today:
            buttons.append(show_today_btn)

        reply_markup = InlineKeyboardMarkup([buttons])
        self.activity.reply_or_update_host_message(reply_text, reply_markup, parse_mode=ParseMode.HTML)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == show_graph_btn.callback_data:
            self.show_graph = True
            self.execute_state()
        elif response_data == hide_graph_btn.callback_data:
            self.show_graph = False
            self.execute_state()
        elif response_data == show_today_btn.callback_data:
            self.target_date = datetime.datetime.now(tz=fitz).date()
            self.execute_state()
        elif response_data == show_tomorrow_btn.callback_data:
            self.target_date = datetime.datetime.now(tz=fitz).date() + datetime.timedelta(days=1)
            self.execute_state()
        elif response_data == info_btn.callback_data:
            self.activity.change_state(SahkoInfoState(last_state=self))


class SahkoInfoState(ActivityState):
    def __init__(self, last_state: ActivityState):
        super().__init__()
        self.last_state = last_state

    def execute_state(self, **kwargs):
        reply_markup = InlineKeyboardMarkup([[back_button]])
        self.activity.reply_or_update_host_message(sahko_command_info, reply_markup,
                                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == back_button.callback_data:
            self.activity.change_state(self.last_state)


sahko_command_info = 'Hintadata on Pohjoismaiden ja Baltian maiden sähköpörssissä Nordpoolissa määräytynyt sähkön ' \
                     'spot hinta. Päivän jokaiselle tunnille määräytyy kaupankäynnissä aina oma hintansa. ' \
                     'Seuraavan päivän hinnat julkaistaan n. klo 13.45 Suomen aikaa. Viestin painikkeissa näkyy ' \
                     'vaihtoehto katsoa seuraavan päivän tietoja, jos ne ovat jo saatavilla. Taulukossa näkyvä ' \
                     'seitsemän päivän keskiarvo sisältää tarkasteluvuorokauden ja sitä edeltävät kuusi vuorokautta. ' \
                     'Lisätietoa ja tarkemman graafin löydät osoitteesta <a href="https://sahko.tk/">sahko.tk</a>.'

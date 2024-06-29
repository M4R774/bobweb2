import datetime
import logging

from aiohttp import ClientResponseError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.constants import ParseMode

from bobweb.bob import command_service, database
from bobweb.bob.activities.activity_state import ActivityState, back_button
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.nordpool_service import DayData, get_data_for_date, get_vat_str, get_vat_by_date, \
    cache_has_data_for_tomorrow, default_graph_width, PriceDataNotFoundForDate
from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.utils_common import send_bot_is_typing_status_update

logger = logging.getLogger(__name__)


class SahkoCommand(ChatCommand):

    def __init__(self):
        super().__init__(
            name='sahko',
            regex=regex_simple_command('sähkö'),
            help_text_short=('!sahko', 'Sähkön hinta')
        )

    def is_enabled_in(self, chat):
        return True

    async def handle_update(self, update: Update, context: CallbackContext = None):
        await send_bot_is_typing_status_update(update.effective_chat)
        await command_service.instance.start_new_activity(update, SahkoBaseState())


# Buttons for SahkoBaseState
show_graph_btn = InlineKeyboardButton(text='Näytä 📊', callback_data='/show_graph')
hide_graph_btn = InlineKeyboardButton(text='Piilota 📊', callback_data='/hide_graph')
graph_width_add_btn = InlineKeyboardButton(text='Levennä', callback_data='/graph_width_add')
graph_width_sub_btn = InlineKeyboardButton(text='Kavenna', callback_data='/graph_width_sub')
show_tomorrow_btn = InlineKeyboardButton(text='Huominen ⏩', callback_data='/show_tomorrow')
show_today_btn = InlineKeyboardButton(text='Tänään ⏪', callback_data='/show_today')
info_btn = InlineKeyboardButton(text='Info ⁉', callback_data='/show_info')

fetch_failed_msg_res_status_code_5xx = 'Norpool API ei ole juuri nyt saatavilla. Yritä myöhemmin uudelleen.'
fetch_failed_msg = 'Sähkön hintojen haku epäonnistui 🔌✂️'
fetch_successful_missing_data = 'Sähkön hintojen haku onnistui, mutta toimitettu hintadata on puutteellista 🧮'


class SahkoBaseState(ActivityState):
    def __init__(self, show_graph: bool = False, target_date: datetime.date = None):
        super().__init__()
        self.show_graph = show_graph
        self.target_date = target_date
        self.graph_width = None

    def get_chat(self):
        return database.get_chat(self.activity.get_chat_id())

    async def execute_state(self):
        today = datetime.datetime.now(tz=fitz).date()
        if self.target_date is None or self.target_date < today:
            self.target_date = today

        if self.graph_width is None:
            self.graph_width = self.get_chat().nordpool_graph_width or default_graph_width

        try:
            data: DayData = await get_data_for_date(target_date=self.target_date, graph_width=self.graph_width)
            await self.format_and_send_msg(data)
        except PriceDataNotFoundForDate:
            await self.send_or_update_host_message(fetch_successful_missing_data, markup=InlineKeyboardMarkup([[]]))
        except ClientResponseError as e:
            log_msg = f'Nordpool Api error. [status]: {str(e.status)}, [message]: {e.message}'
            logger.exception(log_msg, exc_info=True)
            error_msg = fetch_failed_msg_res_status_code_5xx if str(e.status).startswith('5') else fetch_failed_msg
            await self.send_or_update_host_message(error_msg, markup=InlineKeyboardMarkup([[]]))

    async def format_and_send_msg(self, data: DayData):
        today = datetime.datetime.now(tz=fitz).date()
        description = f'Hinnat yksikössä snt/kWh (sis. ALV {get_vat_str(get_vat_by_date(self.target_date))}%)'

        if self.show_graph:
            reply_text = f'{data.data_array}{data.data_graph}{description}'
            graph_mutate_buttons = [hide_graph_btn]
            if self.graph_width > 1:
                graph_mutate_buttons.append(graph_width_sub_btn)
            if self.graph_width < default_graph_width:
                graph_mutate_buttons.append(graph_width_add_btn)
            button_rows = [graph_mutate_buttons, [info_btn]]
        else:
            reply_text = f'{data.data_array}{description}'
            button_rows = [[show_graph_btn, info_btn]]

        if cache_has_data_for_tomorrow() and self.target_date == today:
            button_rows[-1].append(show_tomorrow_btn)
        elif self.target_date != today:
            button_rows[-1].append(show_today_btn)

        reply_markup = InlineKeyboardMarkup(button_rows)
        await self.send_or_update_host_message(reply_text, reply_markup, parse_mode=ParseMode.HTML)

    async def handle_response(self, response_data: str, context: CallbackContext = None):
        match response_data:
            case show_graph_btn.callback_data:
                self.show_graph = True
                await self.execute_state()
            case hide_graph_btn.callback_data:
                self.show_graph = False
                await self.execute_state()
            case graph_width_add_btn.callback_data:
                await self.change_graph_width(1)
            case graph_width_sub_btn.callback_data:
                await self.change_graph_width(-1)
            case show_today_btn.callback_data:
                self.target_date = datetime.datetime.now(tz=fitz).date()
                await self.execute_state()
            case show_tomorrow_btn.callback_data:
                self.target_date = datetime.datetime.now(tz=fitz).date() + datetime.timedelta(days=1)
                await self.execute_state()
            case info_btn.callback_data:
                await self.activity.change_state(SahkoInfoState(last_state=self))

    async def change_graph_width(self, delta_width: int):
        self.graph_width += delta_width
        chat = self.get_chat()
        chat.nordpool_graph_width = self.graph_width
        chat.save()
        await self.execute_state()


class SahkoInfoState(ActivityState):
    def __init__(self, last_state: ActivityState):
        super().__init__()
        self.last_state = last_state

    async def execute_state(self, **kwargs):
        reply_markup = InlineKeyboardMarkup([[back_button]])
        await self.send_or_update_host_message(sahko_command_info, reply_markup,
                                               parse_mode=ParseMode.HTML,
                                               disable_web_page_preview=True)

    async def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == back_button.callback_data:
            await self.activity.change_state(self.last_state)


sahko_command_info = 'Hintadata on Pohjoismaiden ja Baltian maiden sähköpörssissä Nordpoolissa määräytynyt sähkön ' \
                     'spot hinta. Päivän jokaiselle tunnille määräytyy kaupankäynnissä aina oma hintansa. ' \
                     'Seuraavan päivän hinnat julkaistaan n. klo 13.45 Suomen aikaa. Viestin painikkeissa näkyy ' \
                     'vaihtoehto katsoa seuraavan päivän tietoja, jos ne ovat jo saatavilla. Taulukossa näkyvä ' \
                     'seitsemän päivän keskiarvo sisältää tarkasteluvuorokauden ja sitä edeltävät kuusi vuorokautta. ' \
                     'Lisätietoa ja tarkemman graafin löydät osoitteesta <a href="https://sahko.tk/">sahko.tk</a>.'

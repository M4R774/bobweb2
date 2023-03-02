import datetime
import logging

from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob import command_service
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.nordpool_service import DayData, get_data_for_date, get_vat_str, get_vat_by_date

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
show_graph_btn = InlineKeyboardButton(text='Näytä graafi', callback_data='/show_graph')
hide_graph_btn = InlineKeyboardButton(text='Piilota graafi', callback_data='/hide_graph')

fetch_failed_msg = 'Sähkön hintojen haku epäonnistui 🔌✂️'


class SahkoBaseState(ActivityState):
    def execute_state(self, show_graph: bool = False, target_date: datetime.date = None):
        target_date = target_date or self.activity.initial_update.effective_message.date.date()
        try:
            data: DayData = get_data_for_date(target_date=target_date)
        except Exception as e:
            logger.error(e)
            self.activity.reply_or_update_host_message(fetch_failed_msg, markup=InlineKeyboardMarkup([[]]))
            return

        description = f'Hinnat yksikössä snt/kWh (sis. ALV {get_vat_str(get_vat_by_date(target_date))}%)'

        if show_graph:
            reply_text = f'{data.data_array}{data.data_graph}{description}'
            reply_markup = InlineKeyboardMarkup([[hide_graph_btn]])
        else:
            reply_text = f'{data.data_array}{description}'
            reply_markup = InlineKeyboardMarkup([[show_graph_btn]])

        self.activity.reply_or_update_host_message(reply_text, reply_markup, parse_mode=ParseMode.HTML)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == show_graph_btn.callback_data:
            self.execute_state(show_graph=True)
        elif response_data == hide_graph_btn.callback_data:
            self.execute_state(show_graph=False)

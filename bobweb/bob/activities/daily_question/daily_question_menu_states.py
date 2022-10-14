from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity


class DQMainMenuState(ActivityState):
    def __init__(self, activity: CommandActivity = None, initial_update: Update = None):
        super().__init__()
        self.activity = activity
        self.initial_update = initial_update

    def execute_state(self):
        reply_text = dq_main_menu_text_body('Valitse toiminto alapuolelta')
        markup = InlineKeyboardMarkup(self.dq_main_menu_buttons())

        if self.activity.host_message is None:
            self.activity.host_message = self.initial_update.message.reply_text(reply_text, reply_markup=markup)
        else:
            self.activity.update_host_message_content(reply_text, markup)

    def dq_main_menu_buttons(self):
        return [[
            InlineKeyboardButton(text='Info', callback_data='info'),
            InlineKeyboardButton(text='Kausi', callback_data='season'),
            InlineKeyboardButton(text='Tilasto', callback_data='stats')
        ]]

    def handle_response(self, response_data: str):
        next_state: ActivityState | None = None
        match response_data:
            case 'info':
                next_state = DQInfoMessageState(self.activity)

        if next_state:
            self.activity.change_state(next_state)


class DQInfoMessageState(ActivityState):
    def execute_state(self):
        reply_text = dq_main_menu_text_body('Infoviesti tähän')
        markup = InlineKeyboardMarkup(self.buttons())
        self.activity.update_host_message_content(reply_text, markup)

    def buttons(self):
        return [[
            InlineKeyboardButton(text='<-', callback_data='back'),
            InlineKeyboardButton(text='Lisää tietoa', callback_data='more'),
            InlineKeyboardButton(text='Komennot', callback_data='commands')
        ]]

    def handle_response(self, response_data: str):
        extended_info_text = None
        match response_data:
            case 'back':
                self.activity.change_state(DQMainMenuState())
                return
            case 'more':
                extended_info_text = dq_main_menu_text_body('Infoviesti tähän\n\nTässä on vähän enemmän infoa')
            case 'commands':
                extended_info_text = dq_main_menu_text_body('Tässä tieto komennoista')
        self.activity.update_host_message_content(extended_info_text)


def dq_main_menu_text_body(state_message_provider):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider()
    return f'-- Päivän kysymys --\n' \
           f'------------------\n' \
           f'{state_msg}'

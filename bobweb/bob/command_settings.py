from typing import List, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat as TelegramChat
from telegram.ext import CallbackContext

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob import database, command_service
from bobweb.bob.utils_common import split_to_chunks, has
from bobweb.web.bobapp.models import Chat


class SettingsCommand(ChatCommand):
    """ Setting command that opens active chat's settings. Displays each toggleable property as a button that can be
        switched on or off by a button press. Settings-menu can be closed after which list of changed values is
        displayed. Closed setting-menu can be reopened by a button press. """
    invoke_on_reply = True

    def __init__(self):
        super().__init__(
            name='asetukset',
            regex=regex_simple_command('asetukset'),
            help_text_short=('!asetukset', 'botin asetukset')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        chat = database.get_chat(update.effective_chat.id)
        activity = CommandActivity(initial_update=update, state=SettingsMenuOpenState(chat))
        command_service.instance.add_activity(activity)


toggleable_property_key = '_enabled'
property_names_fi = dict([
    ('leet_enabled', '1337'),
    ('broadcast_enabled', 'kuulutus'),
    ('proverb_enabled', 'viisaus'),
    ('time_enabled', 'aika'),
    ('weather_enabled', 'sää'),
    ('or_enabled', 'vai'),
    ('free_game_offers_enabled', 'epic games ilmoitukset'),
    ('voice_msg_to_text_enabled', 'ääniviestin automaattinen tekstitys')
])
bool_to_state_char_dict = {True: '✅', False: '❌', None: '❔'}


def get_state_char(bool_value: bool | None) -> str:
    return bool_to_state_char_dict[bool_value]


def create_toggle_button(property_name: str):
    label = f'{get_localized_property_name(property_name)} {get_state_char(None)}'
    return InlineKeyboardButton(text=label, callback_data=property_name)


def get_localized_property_name(model_property_name: str):
    localized_name = property_names_fi.get(model_property_name)
    basic_name = model_property_name.replace(toggleable_property_key, '')
    return localized_name or basic_name


# For each property in Chat model which name contains 'toggleable_property_key' => list of those property names
toggleable_properties = [x for x in Chat.__dict__ if toggleable_property_key in x]
# For each property name listed => create toggle button
toggle_buttons = [create_toggle_button(x) for x in toggleable_properties]


class SettingsMenuOpenState(ActivityState):
    """ Displays toggleable properties  that can be tapped that can be toggled.
        If menu is hid, activity is switched to SettingsMenuClosedState """
    def __init__(self, chat: Chat, changed_properties=None):
        super(SettingsMenuOpenState, self).__init__()
        self.chat = chat
        self.changed_properties: List[BooleanValueChange] = changed_properties or []

    def execute_state(self):
        chat_type_str = get_in_chat_msg_by_chat_type(self.activity.initial_update.effective_chat)
        reply_text = f'Bobin asetukset tässä {chat_type_str}. Voit kytkeä komentoja päälle tai pois päältä ' \
                     f'painamalla niitä. Muutokset asetuksiin tallentuvat välittömästi.'
        for button in toggle_buttons:
            button.text = button.text[:-1] + get_state_char(self.chat.__dict__[button.callback_data])

        toggle_buttons_with_back = [hide_menu_button] + toggle_buttons
        short, long = split_buttons_to_short_and_long_label_lists(toggle_buttons_with_back)
        buttons_in_rows = split_to_chunks(short, 2) + [long]
        
        self.activity.reply_or_update_host_message(reply_text, InlineKeyboardMarkup(buttons_in_rows))

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == hide_menu_button.callback_data:
            closed_state = SettingsMenuClosedState(self.chat, self.changed_properties)
            self.activity.change_state(closed_state)
        elif response_data in toggleable_properties:
            self.toggle_property(response_data)
        else:
            reply_text = f'Tekstivastauksia ei tueta. Muuta asetuksia täppäämällä tai klikkaamalla niiden ' \
                         f'nappeja alapuolelta. Muutokset asetuksiin tallentuvat välittömästi.'
            self.activity.reply_or_update_host_message(reply_text)

    def toggle_property(self, property_name: str):
        old_value = self.chat.__dict__[property_name]
        new_value = not old_value if old_value is not None else True

        # Log setting change
        prev_log = next((x for x in self.changed_properties if x.property_name == property_name), None)
        if has(prev_log) and prev_log.old_value == new_value:
            self.changed_properties.remove(prev_log)
        else:
            new_log = BooleanValueChange(property_name=property_name, old_value=old_value, new_value=new_value)
            self.changed_properties.append(new_log)

        self.chat.__dict__[property_name] = new_value
        self.chat.save()
        reply_markup = self.activity.host_message.reply_markup
        for row in reply_markup.inline_keyboard:
            for button in row:
                if button.callback_data == property_name:
                    button.text = button.text[:-1] + get_state_char(new_value)
        self.activity.reply_or_update_host_message(markup=reply_markup)


def split_buttons_to_short_and_long_label_lists(buttons: List[InlineKeyboardButton]) -> Tuple[List, List]:
    short, long = [], []
    for button in buttons:
        target_list = short if len(button.text) <= 25 else long
        target_list.append(button)
    return short, long


class SettingsMenuClosedState(ActivityState):
    """ Displays changes to the properties done while menu was open during current activity.
        Has button that opens the settings menu again """
    def __init__(self, chat: Chat, changed_properties: List['BooleanValueChange']):
        super(SettingsMenuClosedState, self).__init__()
        self.chat = chat
        self.changed_properties: List[BooleanValueChange] = changed_properties

    def execute_state(self):
        chat_type_str = get_chat_genitive_msg_by_type(self.activity.initial_update.effective_chat)
        if len(self.changed_properties) > 0:
            change_log_list = ''.join([x.format_list_item() for x in self.changed_properties])
            reply_text = f'Tämän {chat_type_str} asetuksia muutettu seuraavasti:\n{change_log_list}'
        else:
            reply_text = f'Ei muutoksia {chat_type_str} asetuksiin'
        markup = InlineKeyboardMarkup([[show_menu_button]])
        self.activity.reply_or_update_host_message(reply_text, markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == show_menu_button.callback_data:
            open_state = SettingsMenuOpenState(self.chat, self.changed_properties)
            self.activity.change_state(open_state)


class BooleanValueChange:
    """ Simple data class that contains single boolean value change for a named property """
    def __init__(self, property_name: str, old_value: bool, new_value: bool):
        self.property_name = property_name
        self.old_value = old_value
        self.new_value = new_value

    def format_list_item(self) -> str:
        return f'- {get_localized_property_name(self.property_name)}: ' \
               f'{get_state_char(self.old_value)} -> {get_state_char(self.new_value)}\n'


def get_in_chat_msg_by_chat_type(chat: TelegramChat):
    return msg_in_private_type_chat if chat.type == 'private' else msg_in_other_type_chat


def get_chat_genitive_msg_by_type(chat: TelegramChat):
    return msg_chat_genitive_private_type_chat if chat.type == 'private' else msg_chat_genitive_other_type_chat


msg_in_private_type_chat = 'keskustelussa'
msg_in_other_type_chat = 'ryhmässä'

msg_chat_genitive_private_type_chat = 'keskustelun'
msg_chat_genitive_other_type_chat = 'ryhmän'

hide_menu_button = InlineKeyboardButton(text='Piilota asetukset', callback_data='/hide_settings')
show_menu_button = InlineKeyboardButton(text='Näytä asetukset', callback_data='/show_settings')

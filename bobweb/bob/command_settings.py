from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob.activities.activity_state import ActivityState, back_button
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob import database, command_service
from bobweb.bob.utils_common import split_to_chunks
from bobweb.web.bobapp.models import Chat


toggleable_property_key = '_enabled'
property_names_fi = dict([
    ('leet_enabled', '1337'),
    ('broadcast_enabled', 'kuulutus'),
    ('proverb_enabled', 'viisaus'),
    ('time_enabled', 'aika'),
    ('weather_enabled', 'sää'),
    ('or_enabled', 'vai'),
    ('free_game_offers_enabled', 'epic games ilmoitukset'),
])


def get_state_char(bool_value: bool | None) -> str:
    if bool_value is True:
        return '✅'
    elif bool_value is False:
        return '❌'
    else:
        return '❔'


def create_toggle_button(property_name: str):
    localized_name = property_names_fi.get(property_name)
    basic_name = property_name.replace(toggleable_property_key, '')
    label = f'{localized_name or basic_name} {get_state_char(None)}'
    return InlineKeyboardButton(text=label, callback_data=property_name)


toggleable_properties = [x for x in Chat.__dict__ if toggleable_property_key in x]
toggle_buttons = [create_toggle_button(x) for x in toggleable_properties]


class SettingsCommand(ChatCommand):
    invoke_on_reply = True

    def __init__(self):
        super().__init__(
            name='asetukset',
            regex=regex_simple_command('asetukset'),
            help_text_short=('!asetukset', 'botin asetukset')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        chat = database.get_chat(update.effective_chat.id)
        activity = CommandActivity(initial_update=update, state=SettingsMenuState(chat))
        command_service.instance.add_activity(activity)


class SettingsMenuState(ActivityState):
    def __init__(self, chat: Chat):
        super(SettingsMenuState, self).__init__()
        self.chat = chat

    def execute_state(self):
        reply_text = f'Bobin asetukset tässä ryhmässä. Voit kytkeä komentoja päälle tai pois päältä.'

        for button in toggle_buttons:
            button.text = button.text[:-1] + get_state_char(self.chat.__dict__[button.callback_data])

        buttons_in_rows_with_back = split_to_chunks([back_button] + toggle_buttons, 2)
        self.activity.reply_or_update_host_message(reply_text, InlineKeyboardMarkup(buttons_in_rows_with_back))

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == back_button.callback_data:
            reply_text = f'Selvä, muutokset tallennettu. Takaisin nukkumaan 🤖💤'
            self.activity.reply_or_update_host_message(reply_text)
            self.activity.done()

        elif response_data in toggleable_properties:
            old_value = self.chat.__dict__[response_data]
            new_value = not old_value if old_value is not None else True
            self.chat.__dict__[response_data] = new_value
            self.chat.save()
            reply_markup = self.activity.host_message.reply_markup
            for row in reply_markup.inline_keyboard:
                for button in row:
                    if button.callback_data == response_data:
                        button.text = button.text[:-1] + get_state_char(new_value)
            self.activity.reply_or_update_host_message(markup=reply_markup)

        else:
            reply_text = f'Bobin asetukset tässä ryhmässä. Voit kytkeä komentoja päälle tai pois päältä.\n' \
                         f'Muuta asetuksia täppäämällä niitä alapuolelta'
            self.activity.reply_or_update_host_message(reply_text)



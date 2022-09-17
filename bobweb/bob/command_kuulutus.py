import string

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand
from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER
from bobweb.bob import database


class KuulutusCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='kuulutus',
            regex=r'(?i)^' + PREFIXES_MATCHER + r'kuulutus($|\s)',
            help_text_short=('!kuulutus', '[on|off]')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.broadcast_toggle_command(update)

    def is_enabled_in(self, chat):
        return True  # This command is always enabled. Chat.broadcast_enabled toggles broadcasts in the chat

    def broadcast_toggle_command(self, update):
        parameter_text = self.get_parameters(update.message.text)
        on_off_boolean = parse_bool_from_parameter(parameter_text)
        chat = database.get_chat(chat_id=update.effective_chat.id)

        if on_off_boolean is not None:
            chat.broadcast_enabled = on_off_boolean
            reply = f'Kuulutukset ovat nyt {is_toggled_msg[on_off_boolean]}.'
        else:
            reply = get_command_help(chat.broadcast_enabled)

        update.message.reply_text(reply, quote=False)
        chat.save()


def parse_bool_from_parameter(parameter: string) -> bool | None:
    if parameter.casefold() == 'on':
        return True
    if parameter.casefold() == 'off':
        return False
    return None


def get_command_help(broadcast_enabled):
    return "Käyttö: \n" \
            "'/kuulutus on' - Kytkee kuulutukset päälle \n" \
            "'/kuulutus off' - Kytkee kuulutukset pois päältä\n" \
            f'Tällä hetkellä kuulutukset ovat {is_toggled_msg[broadcast_enabled]}.'


is_toggled_msg = {
    True: 'päällä',
    False: 'pois päältä',
    None: 'pois päältä'
}
import requests
from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.command import ChatCommand, regex_simple_command


class IpAddressCommand(ChatCommand):
    """
    Command for getting ip-address for the running environment
    """
    def __init__(self):
        super().__init__(
            name='ip',
            regex=regex_simple_command('ip'),  # Note! No command prefix
            help_text_short=None  # Not shown in help command list
        )

    def is_enabled_in(self, chat):
        # Only enabled in error log chat
        error_log_chat = database.get_the_bob().error_log_chat
        return error_log_chat and error_log_chat.id == chat.id

    async def handle_update(self, update: Update, context: CallbackContext = None):
        reply_text = "IP-osoitteen haku epäonnistui."
        try:
            response = requests.get('https://api.ipify.org')
            if response.status_code == 200:
                reply_text = f'IP-osoite on: {response.text} 📟'
            else:
                reply_text += f'\napi.ipify.org vastasi statuksella: {response.status_code}'
        except requests.exceptions.RequestException as e:
            reply_text += f"\nVirhe: {str(e)}"
        await update.effective_chat.send_message(reply_text)



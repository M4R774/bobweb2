import requests
from aiohttp import ClientResponseError
from telegram import Update
from telegram.ext import CallbackContext

from bot import database, async_http
from bot.commands.base_command import BaseCommand, regex_simple_command


class IpAddressCommand(BaseCommand):
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
        error_log_chat = database.get_bot().error_log_chat
        return error_log_chat and error_log_chat.id == chat.id

    async def handle_update(self, update: Update, context: CallbackContext = None):
        reply_text = "IP-osoitteen haku epäonnistui."
        try:
            response = await async_http.get('https://api.ipify.org')
            if response.status == 200:
                ip_address = await response.text(encoding='utf-8')
                reply_text = f'IP-osoite on: {ip_address} 📟'
            else:
                reply_text += f'\napi.ipify.org vastasi statuksella: {response.status}'
        except ClientResponseError as e:
            reply_text += f"\nVirhe: {e.message}"
        await update.effective_chat.send_message(reply_text)



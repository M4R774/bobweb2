from telegram.ext import CallbackContext

from bobweb.bob import message_board_service, database
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.message_board_service import MessageBoard
from telegram import Update

from bobweb.web.bobapp.models import Chat


class PinnedNotificationsCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='ilmoitustaulu',
            regex=regex_simple_command('ilmoitustaulu'),
            help_text_short=('/ilmoitustaulu', 'näyttää ilmoituksia')
        )

    def is_enabled_in(self, chat):
        return True

    async def handle_update(self, update: Update, context: CallbackContext = None):
        await message_board(update, context)


async def message_board(update: Update, context: CallbackContext = None):
    chat_id = update.effective_chat.id

    # First try to find active message board from the service
    current_board = message_board_service.instance.get_board(update.effective_chat.id)

    if current_board:
        # Check if current board is still the latest pinned message
        await context.bot.unpin_chat_message(chat_id, current_board.host_message_id)
        await context.bot.pin_chat_message(chat_id, current_board.host_message_id, disable_notification=True)
        return  # No other action

    # When no board is active for the chat, create a new one and save its message id to database
    chat: Chat = database.get_chat(update.effective_chat.id)
    new_message = await update.effective_chat.send_message('Ilmoitustaulu')

    # TODO: Error handling for cases when bot does not have required privileges
    await context.bot.pin_chat_message(new_message.chat_id, new_message.message_id, disable_notification=True)
    chat.message_board_msg_id = new_message.message_id
    chat.save()
    message_board_service.instance.create_new_board(chat_id, new_message.message_id)




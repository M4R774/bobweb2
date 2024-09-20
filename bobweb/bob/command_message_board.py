from telegram.error import BadRequest
from telegram.ext import CallbackContext

from bobweb.bob import main, message_board_service, database
from bobweb.bob.command import ChatCommand, regex_simple_command, regex_simple_command_with_parameters
from telegram import Update

from bobweb.bob.utils_common import handle_exception, ignore_message_not_found_telegram_error
from bobweb.web.bobapp.models import Chat


turn_off_message_board_for_chat_command = 'off'
message_board_bad_parameter_help = ('Voit luoda chattiin uuden ilmoitustaulun komennolla \'/ilmoitustaulu\' '
                                    'tai kytkeä sen pois käytöstä komennolla \'/ilmoitustaulu off\'')


class MessageBoardCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='ilmoitustaulu',
            regex=regex_simple_command_with_parameters('ilmoitustaulu'),
            help_text_short=('/ilmoitustaulu', 'näyttää ilmoituksia')
        )

    def is_enabled_in(self, chat):
        return True

    async def handle_update(self, update: Update, context: CallbackContext = None):
        parameter = self.get_parameters(update.effective_message.text)
        await message_board(parameter, update, context)


async def message_board(parameter: str, update: Update, context: CallbackContext = None):
    if parameter and parameter != turn_off_message_board_for_chat_command:
        info_message = ('Voit luoda chattiin uuden ilmoitustaulun komennolla \'/ilmoitustaulu\' tai kytkeä sen pois '
                        'käytöstä komennolla \'/ilmoitustaulu off\'')
        await update.effective_chat.send_message(info_message)
        return

    # First try to find active message board from the service. If the board existed when the bot was started,
    # the board exists in memory in the service and the message will be pinned.
    chat_id = update.effective_chat.id
    current_board = message_board_service.find_board(chat_id)

    if parameter == turn_off_message_board_for_chat_command and current_board:
        with ignore_message_not_found_telegram_error():
            await context.bot.unpin_chat_message(chat_id, current_board.host_message_id)
        # Remove from the service and the database
        message_board_service.instance.remove_board_from_service_and_chat(current_board)
        await update.effective_chat.send_message('Ilmoitustaulu poistettu käytöstä')
        return
    elif current_board:
        with ignore_message_not_found_telegram_error():
            # Repin the board on the chat
            await context.bot.unpin_chat_message(chat_id, current_board.host_message_id)
            await context.bot.pin_chat_message(chat_id, current_board.host_message_id, disable_notification=True)
            return  # No other action

    # When no board is active for the chat, create a new one and save its message id to database
    chat: Chat = database.get_chat(update.effective_chat.id)
    new_message = await update.effective_chat.send_message('Ilmoitustaulu')

    # TODO: Error handling for cases when bot does not have required privileges
    await new_message.pin(disable_notification=True)  # Shortcut method
    chat.message_board_msg_id = new_message.message_id
    chat.save()

    await message_board_service.instance.create_new_board(chat_id, new_message.message_id)




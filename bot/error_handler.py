import asyncio
import html
import json
import logging
import traceback

import telegram.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackContext

import bot.main
from bot import database, message_board_service, utils_common, command_service
from bot.activities.activity_state import ActivityState
from bot.message_board import MessageBoard
from bot.resources import bob_constants
from bot.resources.unicode_emoji import get_random_emoji

logger = logging.getLogger(__name__)

remove_details_timeout_seconds = 3600  # 1 hour
error_msg_to_users_start = ('Virhe 🚧 tunnisteella {}.\n'
                            'Sallitko seuraavien tietojen jakamisen ylläpidolle?')
error_confirmation = ('Valitessasi ei, näytetyt tiedot poistetaan ja ylläpidolle ilmoitetaan vain virheen tunniste '
                      'ja virheen aiheuttanut proseduuri koodissa. Määräaika tietojen lähettämiselle on yksi tunti '
                      'jonka jälkeen ne poistetaan automaattisesti')
error_confirmation_deny = ('Asia selvä! Virheen {} tiedot poistettu ja ylläpitoa on informoitu sen aiheuttaneesta koodi proseduurista')
error_confirmation_allow = 'Kiitoksia! Virhe {} toimitettu tarkempine tietoineen ylläpidolle'
error_confirmation_timeout = 'Virheen tarkemmat tiedot on poistettu automaattisesti määräajan umpeuduttua'
error_confirmation_only_allowed_for_user = '🚫 Stop tykkänään! Valinnan voi tehdä vain käyttäjä jonka tiedot ovat virheessä'

# Inline keyboard constant buttons
deny_button = InlineKeyboardButton(text='En salli', callback_data='/deny')
allow_button = InlineKeyboardButton(text='Sallin', callback_data='/allow')


class ErrorSharingPermissionState(ActivityState):

    def __init__(self,
                 user_id: int,
                 emoji_id: str,
                 error_details_to_user: str,
                 error_details_to_developers: str,
                 traceback_message_id: telegram.Message | None):
        super().__init__(None)
        self.user_id: int = user_id
        self.emoji_id: str = emoji_id
        self.error_details_to_user: str = error_details_to_user
        self.error_details_to_developers: str = error_details_to_developers
        self.traceback_message_id = traceback_message_id
        self.automatic_delete_task: asyncio.Task | None = None

    async def execute_state(self):
        await self.start_automatic_delete_process()
        message = self.create_message_body('\n' + self.error_details_to_user)
        keyboard = InlineKeyboardMarkup([[deny_button, allow_button]])
        await self.send_or_update_host_message(message, keyboard, parse_mode=ParseMode.HTML)

    def create_message_body(self, detail_description: str) -> str:
        return f'{error_msg_to_users_start.format(self.emoji_id)}\n{detail_description}\n\n{error_confirmation}'

    async def start_automatic_delete_process(self):
        self.automatic_delete_task = asyncio.get_running_loop().create_task(self.delete_error_details())

    async def delete_error_details(self):
        await asyncio.sleep(remove_details_timeout_seconds)
        self.clean_up_details()
        await self.send_or_update_host_message(error_confirmation_timeout, markup=None)
        await self.activity.done()

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        # If not the user whos action caused the error and who's details are in the error message,
        # then add notification to the confirmation
        if update.effective_user.id != self.user_id:
            message = (self.create_message_body('\n' + self.error_details_to_user)
                       + '\n\n' + error_confirmation_only_allowed_for_user)
            await self.send_or_update_host_message(message, parse_mode=ParseMode.HTML)
            return

        match response_data:
            case deny_button.callback_data:
                self.automatic_delete_task.cancel()
                self.clean_up_details()
                message = error_confirmation_deny.format(self.emoji_id)
                await self.send_or_update_host_message(message, markup=InlineKeyboardMarkup([]))
                await self.activity.done()

            case allow_button.callback_data:
                self.automatic_delete_task.cancel()
                message = error_confirmation_allow.format(self.emoji_id)
                await self.send_or_update_host_message(message, markup=InlineKeyboardMarkup([]))
                await send_message_to_error_log_chat(update.get_bot(),
                                                     self.error_details_to_developers,
                                                     ParseMode.HTML,
                                                     reply_to=self.traceback_message_id)
                self.clean_up_details()
                await self.activity.done()

    def clean_up_details(self):
        """ Cleans up error details from this state """
        self.emoji_id = ''
        self.error_details_to_user = ''
        self.error_details_to_developers = ''


async def unhandled_bot_exception_handler(update: object, context: CallbackContext) -> None:
    """
    General error handler for all unexpected errors. Logs error with traceback, asks user if they give permission
    to share error details to developers user by replying to the message and if given, sends error details to the
    error log chat.
    """
    # Log the error before we do anything else, so we can see it even if something breaks in error handling
    error_emoji_id = get_random_emoji() + get_random_emoji() + get_random_emoji()
    logger.error(f"Exception while handling an update (id={error_emoji_id}):", exc_info=context.error)

    if update is not None and isinstance(update, Update):
        remove_message_board_message_if_exists(update)
        traceback_str = create_error_traceback_message(context, error_emoji_id)
        traceback_message: telegram.Message | None = await send_message_to_error_log_chat(bot=context.bot,
                                                                                          text=traceback_str,
                                                                                          parse_mode=ParseMode.HTML)
        # Start chat activity that asks user for permission to share error details with developers
        error_details_to_user = utils_common.wrap_html_expandable_quote(create_error_details_for_user(update))
        error_details_to_developers = create_error_details_message(update, error_emoji_id)

        confirmation_state = ErrorSharingPermissionState(update.effective_user.id,
                                                         error_emoji_id,
                                                         error_details_to_user,
                                                         error_details_to_developers,
                                                         traceback_message.id if traceback_message else None)
        await command_service.instance.start_new_activity(update, context, confirmation_state)


async def send_message_to_error_log_chat(bot: Bot,
                                         text: str,
                                         parse_mode: ParseMode = None,
                                         reply_to: int | None = None) -> telegram.Message | None:
    """ Send message to error log chat if such is defined in the database. """
    error_log_chat = database.get_bot().error_log_chat
    if error_log_chat is not None and bot is not None:
        try:
            return await bot.send_message(chat_id=error_log_chat.id, text=text, parse_mode=parse_mode,
                                          reply_to_message_id=reply_to)
        except telegram.error.BadRequest as e:
            logger.error('Exception while sending message to error log chat. '
                         'Tried to send message to chat id=' + str(error_log_chat.id), exc_info=e)
    return None


def create_error_details_for_user(update: Update) -> str | None:
    chat_name = html.escape(update.effective_chat.title) if update.effective_chat.title else 'Yksityisviesti'
    datetime_str = utils_common.fitzstr_from(update.effective_message.date, bob_constants.FINNISH_DATE_TIME_FORMAT)
    return (
        f'<b>Käyttäjätunnus tai nimesi:</b> {html.escape(update.effective_message.from_user.name)}\n'
        f'<b>Chat:</b> {chat_name}\n'
        f'<b>Virheen ajankohta:</b> {datetime_str}\n'
        f'<b>Virheen aiheuttaneen viestin sisältö:</b>\n"<i>{html.escape(update.effective_message.text)}</i>"'
    )


def create_error_traceback_message(context: ContextTypes.DEFAULT_TYPE, error_emoji_id: str) -> str:
    """ Creates error report message """
    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    traceback_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    traceback_string = "".join(traceback_list)

    return (
        f"An exception was raised while handling an update (user given emoji id={error_emoji_id}):\n"
        f"<pre>{html.escape(traceback_string)}</pre>"
    )


def create_error_details_message(update: Update, error_emoji_id: str) -> str:
    error_details = html.escape(json.dumps(update.to_dict(), indent=2, ensure_ascii=False))
    return (f"Error details shared by user ({error_emoji_id}):\n<pre>{error_details}</pre>"
            )


def remove_message_board_message_if_exists(update: Update):
    """ Finds message board related to the chat and requests removal of error causing message """
    message_board: MessageBoard = message_board_service.find_board(chat_id=update.effective_chat.id)
    if message_board:
        message_board.remove_event_by_message_id(update.effective_message.message_id)

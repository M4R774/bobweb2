import html
import json
import logging
import traceback

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bobweb.bob import database
from bobweb.bob.resources.unicode_emoji import get_random_emoji

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    General error handler for all unexpected errors. Logs error, notifies user by replying to the message
    that caught the error and sends traceback to the developer chat.
    """
    error_emoji_id = get_random_emoji() + get_random_emoji() + get_random_emoji()

    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(f"Exception while handling an update (id={error_emoji_id}):", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)

    chat_data_str, user_data_str = '', ''
    if context.chat_data:
        chat_data_str = f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
    if context.user_data:
        user_data_str = f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"

    message = (
        f"An exception was raised while handling an update (user given emoji id={error_emoji_id}):\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"{chat_data_str}"
        f"{user_data_str}"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Send error message to the error log chat if it is set
    error_log_chat = database.get_the_bob().error_log_chat
    if error_log_chat is not None:
        await context.bot.send_message(chat_id=error_log_chat.id, text=message, parse_mode=ParseMode.HTML)

    # And notify users by replying to the message that caused the error
    error_msg_to_users = f'Virhe 🚧 Asiasta ilmoitettu ylläpidolle tunnisteella {error_emoji_id}'
    if isinstance(update, Update):
        await update.effective_message.reply_text(error_msg_to_users, quote=True)



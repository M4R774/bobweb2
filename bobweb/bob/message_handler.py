import logging
import random
from typing import List, Any

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import database, command_service, message_handler_voice, message_board_service
from bobweb.bob import git_promotions
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_daily_question import check_and_handle_reply_to_daily_question
from bobweb.bob.message_board import NotificationMessage
from bobweb.bob.utils_common import has, has_no
logger = logging.getLogger(__name__)


async def handle_update(update: Update, context: CallbackContext = None):
    if update.effective_message is None:
        return

    database.update_chat_in_db(update)
    database.update_user_in_db(update)

    if update.effective_message.voice or update.effective_message.video_note:
        # Voice messages are handled by another module
        await message_handler_voice.handle_voice_or_video_note_message(update)

    if update.effective_message.caption:
        # If update contains media content and message text is in a caption attribute. Set caption to text attribute,
        # so that the message is handled same way as messages without media content. However, as since PTB 20.0
        # all PTB classes are immutable, we have to use this 'hack' of unfreezing the message-object. This is not
        # recommended or supported by PTB, but it resolves the issue.
        with update.effective_message._unfrozen() as unfrozen_message:
            unfrozen_message.text = update.effective_message.caption

    if update.effective_message.text:

        # FOR TESTING [
        # message_board = message_board_service.instance.get_board(update.effective_chat.id)
        # if has(message_board):
        #     await message_board.set_default_msg(update.effective_message.text)
        # ] FOR TESTING

        await process_update(update, context)


async def process_update(update: Update, context: CallbackContext = None):
    enabled_commands = resolve_enabled_commands(update)
    command: ChatCommand = find_first_matching_enabled_command(update, enabled_commands)

    if has(command):
        await command.handle_update(update, context)
    elif has(update.effective_message.reply_to_message):
        await reply_handler(update, context)
    else:

        # FOR TESTING [
        board = message_board_service.instance.find_board(update.effective_message.chat_id)
        notification: NotificationMessage = NotificationMessage(message=update.effective_message.text)
        board.add_notification(notification)
        # ] FOR TESTING

        await low_probability_reply(update)


def resolve_enabled_commands(update) -> List[ChatCommand]:
    # Returns list of commands that are enabled in the chat of the update
    chat = database.get_chat(update.effective_chat.id)
    commands = command_service.instance.commands
    return [command for command in commands if command.is_enabled_in(chat)]


def find_first_matching_enabled_command(update: Update, enabled_commands: List[ChatCommand]) -> Any | None:
    message_text = update.effective_message.text
    for command in enabled_commands:
        # checks if command should invoke on message edits and/or replies
        edit_ok = command.invoke_on_edit or has_no(update.edited_message)
        reply_ok = command.invoke_on_reply or has_no(update.effective_message.reply_to_message)
        if command.regex_matches(message_text) and edit_ok and reply_ok:
            return command
    # If no command matches regex or matched command should not handle message reply and/or edit
    return None


async def reply_handler(update: Update, context: CallbackContext = None):
    # Test if reply target is active commandActivity. If so, it will handle the reply.
    handled = await command_service.instance.reply_and_callback_query_handler(update, context)
    if handled:
        return

    # Test if reply target is current days daily question. If so, save update as answer
    handled = await check_and_handle_reply_to_daily_question(update, context)
    if handled:
        return

    reply_to_message = update.effective_message.reply_to_message
    is_reply_to_bob = has(context) and reply_to_message.from_user.id == context.bot.id
    if is_reply_to_bob:
        message_text = reply_to_message.text
        if message_text and message_text.startswith("Git käyttäjä "):
            await git_promotions.process_entities(update)


async def low_probability_reply(update):
    random_int = random.randint(1, 10000)  # NOSONAR # 0,01% probability
    if random_int == 1:
        reply_text = "Vaikuttaa siltä että olette todella onnekas " + "\U0001F340"  # clover emoji
        await update.effective_message.reply_text(reply_text)

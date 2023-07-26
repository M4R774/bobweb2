import asyncio
import logging
import random
from typing import List, Any
import threading

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import database, command_service, message_handler_voice
from bobweb.bob import git_promotions
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_daily_question import check_and_handle_reply_to_daily_question
from bobweb.bob.utils_common import has, has_no, reply_as_task

logger = logging.getLogger(__name__)


async def handle_update(update: Update, context: CallbackContext = None):
    if update.effective_message is None:
        return

    database.update_chat_in_db(update)
    database.update_user_in_db(update)

    if update.effective_message.voice or update.effective_message.video_note:
        # Voice messages are handled by another module
        message_handler_voice.handle_voice_or_video_note_message(update)

    if update.effective_message.caption:
        # Update contains image media and message text is in caption attribute.
        # Set caption to text attribute, so that the message is handled same way as messages without image media.
        update.effective_message.text = update.effective_message.caption

    if update.effective_message.text:
        await process_update(update, context)


async def process_update(update: Update, context: CallbackContext = None):
    enabled_commands = resolve_enabled_commands(update)
    command: ChatCommand = find_first_matching_enabled_command(update, enabled_commands)

    if has(command):
        await command.handle_update(update, context)
    elif has(update.effective_message.reply_to_message):
        reply_handler(update, context)
    else:
        low_probability_reply(update)


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


def reply_handler(update: Update, context: CallbackContext = None):
    # Test if reply target is active commandActivity. If so, it will handle the reply.
    command_service.instance.reply_and_callback_query_handler(update, context)
    # Test if reply target is current days daily question. If so, save update as answer
    check_and_handle_reply_to_daily_question(update, context)

    is_reply_to_bob = has(context) and update.effective_message.reply_to_message.from_user.id == context.bot.id
    if is_reply_to_bob:
        if update.effective_message.reply_to_message.text.startswith("Git käyttäjä "):
            git_promotions.process_entities(update)


def low_probability_reply(update, integer=0):  # added int argument for unit testing
    if integer == 0:
        random_int = random.randint(1, 10000)  # NOSONAR # 0,01% probability
    else:
        random_int = integer
    if random_int == 1:
        reply_text = "Vaikuttaa siltä että olette todella onnekas " + "\U0001F340"  # clover emoji
        reply_as_task(update, reply_text)

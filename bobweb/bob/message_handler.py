import logging
import random
from typing import List, Any

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import database, command_service

from bobweb.bob import git_promotions
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_daily_question import check_and_handle_reply_to_daily_question

logger = logging.getLogger(__name__)


def message_handler(update: Update, context: CallbackContext = None):
    database.update_chat_in_db(update)
    database.update_user_in_db(update)

    if update.message is not None and update.message.text is not None:
        if update.message.reply_to_message is not None:
            reply_handler(update, context)
        else:
            command_handler(update, context)


def reply_handler(update: Update, context: CallbackContext = None):
    # Test if reply target is active commandActivity. If so, it will handle the reply.
    command_service.command_service_instance.reply_and_callback_query_handler(update, context)
    # Test if reply target is current days daily question. If so, save update as answer
    check_and_handle_reply_to_daily_question(update)

    if update.message.reply_to_message.from_user.is_bot:
        if update.message.reply_to_message.text.startswith("Git käyttäjä "):
            git_promotions.process_entities(update)


def command_handler(update: Update, context: CallbackContext = None):
    enabled_commands = resolve_enabled_commands(update)

    command: ChatCommand = find_first_matching_enabled_command(update.message.text, enabled_commands)
    if command is not None:
        command.handle_update(update, context)  # Invoke command handler
    else:
        low_probability_reply(update)


def resolve_enabled_commands(update) -> List[ChatCommand]:
    chat = database.get_chat(update.effective_chat.id)
    commands = command_service.command_service_instance.commands
    return [command for command in commands if command.is_enabled_in(chat)]


def find_first_matching_enabled_command(message, enabled_commands) -> Any | None:
    for command in enabled_commands:
        if command.regex_matches(message):
            return command

    # No regex match in enabled commands
    return None


def low_probability_reply(update, integer=0):  # added int argument for unit testing
    if integer == 0:
        random_int = random.randint(1, 10000)  # NOSONAR # 0,01% probability
    else:
        random_int = integer
    if random_int == 1:
        reply_text = "Vaikuttaa siltä että olette todella onnekas " + "\U0001F340"  # clover emoji
        update.message.reply_text(reply_text, quote=True)


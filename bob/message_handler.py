import logging
import random
from typing import List, Any

from telegram import Update

import database

import main
import git_promotions
import command_service
from abstract_command import AbstractCommand

logger = logging.getLogger(__name__)


def commands():  # All BOB's chat commands
    return command_service.CommandService()


def message_handler(update: Update, context=None):
    del context
    database.update_chat_in_db(update)
    database.update_user_in_db(update)

    if update.message is not None and update.message.text is not None:
        if update.message.reply_to_message is not None:
            reply_handler(update)

        command_handler(update)


def reply_handler(update):
    if update.message.reply_to_message.from_user.is_bot:
        # Reply to bot, so most probably to me! (TODO: Figure out my own ID and use that instead)
        if update.message.reply_to_message.text.startswith("Git käyttäjä "):
            git_promotions.process_entities(update)


def command_handler(update):
    enabled_commands = resolve_enabled_commands(update)

    command: AbstractCommand = find_first_matching_enabled_command(update.message.text, enabled_commands)
    if command is not None:
        command.handle_update(update)  # Invoke command handler
    else:
        low_probability_reply(update)


def resolve_enabled_commands(update) -> List[AbstractCommand]:
    chat = database.get_chat(update.effective_chat.id)
    return [command for command in commands() if command.is_enabled_in(chat)]


def find_first_matching_enabled_command(message, enabled_commands) -> Any | None:
    for command in enabled_commands:
        if command.regex_matches(message):
            return command

    # No regex match in enabled commands
    return None


async def broadcast_command(update):
    message = update.message.text
    await main.broadcast(update.bot, message)


def low_probability_reply(update, integer=0):  # added int argument for unit testing
    if integer == 0:
        random_int = random.randint(1, 10000)  # 0,01% probability
    else:
        random_int = integer
    if random_int == 1:
        reply_text = "Vaikuttaa siltä että olette todella onnekas " + "\U0001F340"  # clover emoji
        update.message.reply_text(reply_text, quote=True)


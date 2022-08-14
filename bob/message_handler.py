import datetime
import logging
import random
import re
from typing import List, Any
from zoneinfo import ZoneInfo

import pytz
import requests
from telegram import Update

import database
import rules_of_acquisition
import main
import git_promotions
from command_service import CommandService
from abstract_command import AbstractCommand
from ranks import ranks
from weather_command import weather_command
from bob.help_command import HelpCommand

logger = logging.getLogger(__name__)


# def commands():  # All BOB's chat commands
#     return [
        # "1337": {
        #     REGEX: r'^1337$',
        #     HANDLER: leet_command,
        #     ENABLER: lambda chat: chat.leet_enabled,
        #     HELP_TEXT: ('1337', 'Nopein ylenee')
        # },
        # "käyttäjät": {
        #     REGEX: r'' + PREFIXES_MATCHER + 'käyttäjät',
        #     HANDLER: users_command,
        #     HELP_TEXT: ('!käyttäjät', 'Lista käyttäjistä')
        # },
        # "ruoka": {
        #     REGEX: r'' + PREFIXES_MATCHER + 'ruoka',
        #     HANDLER: ruoka_command,
        #     ENABLER: lambda chat: chat.ruoka_enabled,
        #     HELP_TEXT: ('!ruoka', 'Ruokaresepti')
        # },
        # "space": {
        #     REGEX: r'' + PREFIXES_MATCHER + 'space',
        #     HANDLER: space_command,
        #     ENABLER: lambda chat: chat.space_enabled,
        #     HELP_TEXT: ('!space', 'Seuraava laukaisu')
        # },
        # "kuulutus": {
        #     REGEX: r'' + PREFIXES_MATCHER + 'kuulutus',
        #     HANDLER: broadcast_toggle_command,
        #     ENABLER: lambda chat: chat.broadcast_enabled,
        #     HELP_TEXT: ('!kuulutus', '[on|off]')
        # },
        # "aika": {
        #     REGEX: r'' + PREFIXES_MATCHER + 'aika',
        #     HANDLER: time_command,
        #     ENABLER: lambda chat: chat.time_enabled,
        #     HELP_TEXT: ('!aika', 'Kertoo ajan')
        # },
        # "sääntö": {
        #     REGEX: r'' + PREFIXES_MATCHER + 'sääntö',
        #     HANDLER: rules_of_acquisition_command,
        #     HELP_TEXT: ('!sääntö', '[nro] Hankinnan sääntö')
        # },
        # "sää": {
        #     REGEX: r'' + PREFIXES_MATCHER + 'sää',
        #     HANDLER: weather_command,
        #     ENABLER: lambda chat: chat.weather_enabled,
        #     HELP_TEXT: ('!sää', '[kaupunki]:n sää')
        # },
        # "vai": {
        #     REGEX: r'.*\s.vai\s.*',  # any text and whitespace before and after the command
        #     HANDLER: or_command,
        #     ENABLER: lambda chat: chat.or_enabled,
        #     HELP_TEXT: ('.. !vai ..', 'Arpoo jomman kumman')
        # },
        # "huutista": {
        #     REGEX: r'(?i)huutista',  # (?i) => case insensitive
        #     HANDLER: lambda update: update.message.reply_text('...joka tuutista! 😂'),
        #     ENABLER: lambda chat: chat.huutista_enabled,
        #     HELP_TEXT: ('huutista', '😂')
        # },
    #     HelpCommand(commands())
    # ]

def commands():
    return CommandService.commands


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


def ruoka_command(update: Update) -> None:
    """
    Send a message when the command /ruoka is issued.
    Returns link to page in https://www.soppa365.fi
    """
    with open("recipes.txt", "r") as recipe_file:
        recipes = recipe_file.readlines()

    reply_text = random.choice(recipes)

    update.message.reply_text(reply_text, quote=False)


def space_command(update: Update) -> None:
    """
    Send a message when the command /space is issued.
    Queries next spacex launch time from public API:
    https://github.com/r-spacex/SpaceX-API
    """
    helsinki_tz = ZoneInfo('Europe/Helsinki')
    try:
        r = requests.get('https://api.spacexdata.com/v4/launches/next')
        r = r.json()
        name = r.get('name', None)
        launch_date = r.get('date_utc', None)
        waiting_time = "T-: "
        if launch_date:
            launch_date = datetime.datetime.fromisoformat(launch_date[:-1])
            delta = launch_date - datetime.datetime.now()
            days, hours, minutes = delta.days, delta.seconds // 3600, delta.seconds // 60 % 60
            if days > 0:
                waiting_time += "{} päivää, ".format(days)
            if hours > 0:
                waiting_time += "{} tuntia ja ".format(hours)
            if minutes > 0:
                waiting_time += "{} minuuttia.".format(minutes)
            launch_date = launch_date.astimezone(helsinki_tz).strftime('%d.%m.%Y klo %H:%M:%S (Helsinki)')
        reply_text = 'Seuraava SpaceX laukaisu {}:\n{}\n{}\n'.format(name, launch_date, waiting_time)
    except requests.exceptions.RequestException:
        reply_text = 'Ei tietoa seuraavasta lähdöstä :( API ehkä rikki.'

    update.message.reply_text(reply_text, quote=False)


def users_command(update: Update):
    chat_members = database.get_chat_members_for_chat(chat_id=update.effective_chat.id)
    reply_text = ""
    # code in place if we want to get the chat name and use it
    # chat_name = str(update.effective_chat.title)
    # if chat_name != "None":
    #    reply_text = chat_name + " -ryhmän käyttäjät " + "\U0001F913 " + "\n" + "\n"
    # else:
    #    reply_text = "Käyttäjät " + "\U0001F913 " + "\n" + "\n"
    reply_text = "*Käyttäjät* " + "\U0001F913 " + "\n" + "\n" + \
                 "*Nimi* ⌇ Arvo ⌇ Kunnia ⌇ Viestit" + "\n"  # nerd face emoji
    for chat_member in chat_members:
        reply_text += "*" + str(chat_member) + " ⌇*" + " " + \
                      str(chat_member.rank) + " ⌇ " + \
                      str(chat_member.prestige) + " ⌇ " + \
                      str(chat_member.message_count) + "\n"
    update.message.reply_markdown(reply_text, quote=False)


def broadcast_toggle_command(update):
    chat = database.get_chat(chat_id=update.effective_chat.id)
    if update.message.text.casefold() == "/kuulutus on".casefold():
        chat.broadcast_enabled = True
        update.message.reply_text("Kuulutukset ovat nyt päällä tässä ryhmässä.", quote=False)
    elif update.message.text.casefold() == "/kuulutus off".casefold():
        chat.broadcast_enabled = False
        update.message.reply_text("Kuulutukset ovat nyt pois päältä.", quote=False)
    else:
        update.message.reply_text("Käyttö: \n"
                                  "'/kuulutus on' - Kytkee kuulutukset päälle \n"
                                  "'/kuulutus off' - Kytkee kuulutukset pois päältä\n")
        if chat.broadcast_enabled:
            update.message.reply_text("Tällä hetkellä kuulutukset ovat päällä.", quote=False)
        else:
            update.message.reply_text("Tällä hetkellä kuulutukset ovat pois päältä.", quote=False)
    chat.save()


async def broadcast_command(update):
    message = update.message.text
    await main.broadcast(update.bot, message)


def time_command(update: Update):
    date_time_obj = date_time_obj = datetime.datetime.now(pytz.timezone('Europe/Helsinki')).strftime('%H:%M:%S.%f')[:-4]
    time_stamps_str = str(date_time_obj)
    reply_text = '\U0001F551 ' + time_stamps_str
    update.message.reply_text(reply_text, quote=False)


def or_command(update):
    options = re.split(r'\s.vai\s', update.message.text)
    options = [i.strip() for i in options]
    reply = random.choice(options)
    reply = reply.rstrip("?")
    if reply and reply is not None:
        update.message.reply_text(reply)


def rules_of_acquisition_command(update):
    rule_number = update.message.text.split(" ")[1]
    try:
        update.message.reply_text(rules_of_acquisition.dictionary[int(rule_number)], quote=False)
    except (KeyError, ValueError) as e:
        logger.info("Rule not found with key: \"" + str(e) + "\" Sending random rule instead.")
        random_rule_number = random.choice(list(rules_of_acquisition.dictionary))
        random_rule = rules_of_acquisition.dictionary[random_rule_number]
        update.message.reply_text(str(random_rule_number) + ". " + random_rule, quote=False)


def low_probability_reply(update, integer=0):  # added int argument for unit testing
    if integer == 0:
        random_int = random.randint(1, 10000)  # 0,01% probability
    else:
        random_int = integer
    if random_int == 1:
        reply_text = "Vaikuttaa siltä että olette todella onnekas " + "\U0001F340"  # clover emoji
        update.message.reply_text(reply_text, quote=True)


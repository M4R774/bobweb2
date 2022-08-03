import datetime
import logging
import random
import re
from zoneinfo import ZoneInfo

import pytz
import requests
from telegram import Update

import database
import rules_of_acquisition
import main
import git_promotions
from ranks import ranks
from weather_command import weather_command

logger = logging.getLogger(__name__)


def message_handler(update: Update, context=None):
    del context
    database.update_chat_in_db(update)
    database.update_user_in_db(update)

    if update.message and update.message.text:
        if update.message.reply_to_message is not None:
            reply_handler(update)

        command_handler(update)


def command_handler(update):
    command = resolve_given_command(update)
    enabled_commands = resolve_enabled_commands(update)

    if command_is_available_and_name_or_regex_match(command, enabled_commands, update):
        enabled_commands.get(command)[HANDLER](update)  # Invoke command handler
        return
    elif re.search(r'..*\s.vai\s..*', update.message.text):
        enabled_commands.get('vai')[HANDLER](update)
        return

    low_probability_reply(update)


def resolve_given_command(update):
    # Matches any word that is between optional command_prefix and optional whitespace
    matcher = r"[{}]?(\w*)".format(''.join(command_prefixes))
    match = re.match(matcher, update.message.text)
    return match.group(1).lower() if match and len(match.groups()) > 0 else ""


def resolve_enabled_commands(update):
    chat = database.get_chat(update.effective_chat.id)
    enabled_commands = {}
    for key in commands:
        no_enabler = ENABLER not in commands[key]
        is_enabled = ENABLER in commands[key] and commands[key][ENABLER](chat)

        if no_enabler or is_enabled:
            enabled_commands[key] = commands[key]

    return enabled_commands


def command_is_available_and_name_or_regex_match(command, enabled_commands, update):
    if command in enabled_commands:
        command_obj = enabled_commands.get(command)
        # '^' start of String, '$' end of string => '^text$' requires input to be exactly 'text'
        regex = command_obj[REGEX] if REGEX in command_obj else r'^' + command + '$'
        return re.match(regex, update.message.text)

    return False





def reply_handler(update):
    if update.message.reply_to_message.from_user.is_bot:
        # Reply to bot, so most probably to me! (TODO: Figure out my own ID and use that instead)
        if update.message.reply_to_message.text.startswith("Git käyttäjä "):
            git_promotions.process_entities(update)


def leet_command(update: Update):
    now = datetime.datetime.now(pytz.timezone('Europe/Helsinki'))
    chat = database.get_chat(update.effective_chat.id)
    sender = database.get_chat_member(chat_id=update.effective_chat.id,
                                      tg_user_id=update.effective_user.id)
    if chat.latest_leet != now.date() and \
            now.hour == 13 and \
            now.minute == 37:
        chat.latest_leet = now.date()
        chat.save()
        reply_text = promote(sender)
    else:
        reply_text = demote(sender)
    update.message.reply_text(reply_text, quote=False)


def promote(sender):
    if sender.rank < len(ranks) - 1:
        sender.rank += 1
        up = u"\U0001F53C"
        reply_text = "Asento! " + str(sender.tg_user) + " ansaitsi ylennyksen arvoon " + \
                     ranks[sender.rank] + "! " + up + " Lepo. "
    else:
        sender.prestige += 1
        reply_text = "Asento! " + str(sender.tg_user) + \
                     " on saavuttanut jo korkeimman mahdollisen sotilasarvon! Näin ollen " + str(sender.tg_user) + \
                     " lähtee uudelle kierrokselle. Onneksi olkoon! " + \
                     "Juuri päättynyt kierros oli hänen " + str(sender.prestige) + ". Lepo. "
        sender.rank = 0
    sender.save()
    return reply_text


def demote(sender):
    if sender.rank > 0:
        sender.rank -= 1
    down = u"\U0001F53D"
    reply_text = "Alokasvirhe! " + str(sender.tg_user) + " alennettiin arvoon " + \
                 ranks[sender.rank] + ". " + down
    sender.save()
    return reply_text


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


def help_command(update):
    maxlen = get_longest_command_help_text_name_length()

    command_heading = form_command_with_tab('Komento', maxlen) + 'Selite'
    command_string_list = form_command_help_list(maxlen)

    reply_text = "```\nBob-botti osaa auttaa ainakin seuraavasti:\n\n" \
                 + command_heading + \
                 "\n--------------------------------------\n" \
                 + command_string_list + \
                 "\nEtumerkillä aloitetut komennot voi aloitta joko huutomerkillä, pisteellä tai etukenolla [!./].\n```"
    update.message.reply_text(reply_text, parse_mode='Markdown', quote=False)


def get_longest_command_help_text_name_length():
    maxlen = 0
    for command in commands.values():
        if HELP_TEXT in command and len((command[HELP_TEXT])[0]) > maxlen:
            maxlen = len((command[HELP_TEXT])[0])
    return maxlen


def form_command_help_list(maxlen):
    output_text = ''
    for key in commands:
        if HELP_TEXT in commands[key]:
            command_text = form_command_with_tab((commands[key][HELP_TEXT])[0], maxlen)
            description = (commands[key][HELP_TEXT])[1]
            output_text += command_text + description + '\n'
    return output_text


def form_command_with_tab(text, longest_command_length):
    return text + ' ' * (longest_command_length - len(text)) + ' | '


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


def leaderboard_command(update):
    # TODO
    pass


def low_probability_reply(update, integer=0):  # added int argument for unit testing
    if integer == 0:
        random_int = random.randint(1, 10000)  # 0,01% probability
    else:
        random_int = integer
    if random_int == 1:
        reply_text = "Vaikuttaa siltä että olette todella onnekas " + "\U0001F340"  # clover emoji
        update.message.reply_text(reply_text, quote=True)


def leet_enabled(chat): return chat.leet_enabled
def ruoka_enabled(chat): return chat.ruoka_enabled
def space_enabled(chat): return chat.space_enabled
def broadcast_enabled(chat): return chat.broadcast_enabled
def proverb_enabled(chat): return chat.proverb_enabled
def time_enabled(chat): return chat.time_enabled
def weather_enabled(chat): return chat.weather_enabled
def or_enabled(chat): return chat.or_enabled
def huutista_enabled(chat): return chat.huutista_enabled


# space after command means that parameters are required
HANDLER = 'handler'  # method: receives the message that contained the command
ENABLER = 'enabler'  # method: defines if command is enabled
REGEX = 'regex'  # regex: custom regex to match the command. If empty, strict match to command name
HELP_TEXT = 'help_text'  # tuple: [0]: name [1]: description
command_prefixes = ['.', '/', '!']
prefixes_r = '[{}]'.format(''.join(command_prefixes))

commands = {
    "1337": {
        HANDLER: leet_command,
        HELP_TEXT: ('1337', 'Nopein ylenee')
    },
    "käyttäjät": {
        REGEX: r'' + prefixes_r + 'käyttäjät',
        HANDLER: users_command,
        HELP_TEXT: ('!käyttäjät', 'Lista käyttäjistä')
    },
    "ruoka": {
        REGEX: r'' + prefixes_r + 'ruoka',
        HANDLER: ruoka_command,
        ENABLER: ruoka_enabled,
        HELP_TEXT: ('!ruoka', 'Ruokaresepti')
    },
    "space": {
        REGEX: r'' + prefixes_r + 'space',
        HANDLER: space_command,
        ENABLER: space_enabled,
        HELP_TEXT: ('!space', 'Seuraava laukaisu')
    },
    "kuulutus": {
        REGEX: r'' + prefixes_r + 'kuulutus',
        HANDLER: broadcast_toggle_command,
        ENABLER: broadcast_enabled,
        HELP_TEXT: ('!kuulutus', '[on|off]')
    },
    "aika": {
        REGEX: r'' + prefixes_r + 'aika',
        HANDLER: time_command,
        ENABLER: time_enabled,
        HELP_TEXT: ('!aika', 'Kertoo ajan')
    },
    "sääntö": {
        REGEX: r'' + prefixes_r + 'sääntö',
        HANDLER: rules_of_acquisition_command,
        HELP_TEXT: ('!sääntö', '[nro] Hankinnan sääntö')
    },
    "sää": {
        REGEX: r'' + prefixes_r + 'sää',
        HANDLER: weather_command,
        ENABLER: weather_enabled,
        HELP_TEXT: ('!sää', '[kaupunki]:n sää')
    },
    "tulostaulu": {
        REGEX: r'' + prefixes_r + 'tulostaulu',
        HANDLER: leaderboard_command,
        HELP_TEXT: ('!tulostaulu', 'Näyttää tulostaulun')
    },
    "vai": {
        REGEX: r'.*\s.vai\s.*',  # any text and whitespace before and after the command
        HANDLER: or_command,
        HELP_TEXT: ('.. !vai ..', 'Arpoo jomman kumman')
    },
    "huutista": {
        REGEX: r'(?i)huutista',  # (?i) => case insensitive
        HANDLER: lambda update: update.message.reply_text('...joka tuutista! 😂'),
        HELP_TEXT: ('huutista', '😂')
    },
    "help": {
        REGEX: r'' + prefixes_r + 'help',
        HANDLER: help_command,
    }
}

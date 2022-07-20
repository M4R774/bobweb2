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
import features_toggle
from ranks import ranks
from weather_command import weather_command

logger = logging.getLogger(__name__)


def message_handler(update: Update, context=None):
    del context
    database.update_chat_in_db(update)
    database.update_user_in_db(update)

    if update.message is not None and update.message.text is not None:
        if update.message.reply_to_message is not None:
            reply_handler(update)
        elif update.message.text == "1337":
            leet_command(update)
        elif update.message.text.startswith((".", "/", "!")):
            command_handler(update)
        elif re.search(r'..*\s.vai\s..*', update.message.text) is not None:
            or_command(update)
        elif update.message.text.lower() == "huutista":
            update.message.reply_text('...joka tuutista! 😂')
        else:
            low_probability_reply(update)


def command_handler(update):
    incoming_message_text = update.message.text
    chat = database.get_chat(update.effective_chat.id)

    is_ruoka_command = (incoming_message_text[1:] == "ruoka")
    is_space_command = (incoming_message_text[1:] == "space")
    is_user_command = (incoming_message_text[1:] == "käyttäjät")
    is_feature_toggle_command = incoming_message_text[1:].startswith("kytke")
    is_aika_command = (incoming_message_text[1:] == "aika")
    is_rules_of_acquisition = (incoming_message_text[1:].startswith("sääntö"))
    is_weather_command = incoming_message_text[1:].startswith("sää")
    is_leaderboard_command = (incoming_message_text[1:].startswith("tulostaulu"))

    if update.message.reply_to_message is not None:
        reply_handler(update)
    elif is_ruoka_command and chat.ruoka_enabled:
        ruoka_command(update)
    elif is_space_command and chat.space_enabled:
        space_command(update)
    elif is_user_command:
        users_command(update)  # TODO: Admin vivun taakse
    elif is_feature_toggle_command:
        feature_toggle_command(update)
    elif is_aika_command and chat.time_enabled:
        time_command(update)
    elif is_rules_of_acquisition:
        rules_of_acquisition_command(update)
    elif is_weather_command and chat.weather_enabled:
        weather_command(update)
    elif is_leaderboard_command:
        leaderboard_command(update)


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


# Example usage: ".kytke 1337 off"
def feature_toggle_command(update):
    if is_admin(update) or \
       is_global_admin(update) or \
       not is_group_chat(update):
        try:
            toggle_feature(update)
        except Exception as e:
            print(e)
            chat = database.get_chat(chat_id=update.message.chat_id)
            toggleable_features_dict = features_toggle.get_toggleable_features()
            reply_text = "Käyttö: '.kytke 1337 off' \n\n" \
                         "Kytkettävät ominaisuudet: \n"
            for feature_name, feature_db_field in toggleable_features_dict.items():
                reply_text += feature_name + ": " + bool_to_on_off_string(chat.__dict__[feature_db_field]) + "\n"

            update.message.reply_text(reply_text, quote=False)
    else:
        reply_text = "Sinulla ei ole riittäviä oikeuksia kytkeä ominaisuuksia päälle tai pois. "
        update.message.reply_text(reply_text, quote=False)


def is_admin(update):
    return database.get_chat_member(update.effective_chat.id, update.effective_user.id).admin


def is_global_admin(update):
    return database.get_global_admin().id == update.effective_user.id


def is_group_chat(update):
    return update.message.chat_id < 0


def toggle_feature(update):
    split_message = update.message.text.split()
    desired_state = None
    if len(split_message) >= 3:
        desired_state_string = split_message[2]
        desired_state = on_off_string_to_bool(desired_state, desired_state_string)
    feature_to_toggle = update.message.text.split()[1]
    if feature_to_toggle != "":
        features_toggle.toggle(chat_id=update.effective_chat.id,
                               feature_name_to_toggle=feature_to_toggle,
                               desired_state=desired_state)
        reply_text = "jee onnistui"
        # TODO: Cleanup the printing, eg:
        # 1337: off
        # kuulutus: on
        update.message.reply_text(reply_text, quote=False)
    else:
        raise Exception


def on_off_string_to_bool(on_off_string):
    desired_state = None
    if on_off_string.casefold() == "on":
        desired_state = True
    elif on_off_string.casefold() == "off":
        desired_state = False
    return desired_state


def bool_to_on_off_string(boolean):
    if boolean:
        return "on"
    else:
        return "off"


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

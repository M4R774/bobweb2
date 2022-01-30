#!/usr/bin/env python

import json
import logging
import os
import re
import sys
import random

import pytz
import requests
import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext


sys.path.append('../web')  # needed for sibling import
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)

django.setup()
from bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)
ranks = []
settings_data = {}


def message_handler(update: Update, context: CallbackContext):
    update_chat_in_db(update)
    update_user_in_db(update)
    if update.message.reply_to_message is not None:
        reply_handler(update, context)
    elif update.message.text is None:
        # If the text part is none, eg image, sticker, audio... -> do nothing
        pass
    elif update.message.text == "1337":
        leet_command(update, context)
    elif update.message.text == "/space":
        space_command(update, context)
    elif update.message.text == "/users":
        users_command(update, context)
    elif update.message.text.startswith("/kuulutus"):
        broadcast_toggle_command(update, context)
    elif update.message.text == "/time":
        time_command(update, context)
    elif update.message.text.startswith("/weather"):
        weather_command(update, context)
    elif update.message.text is not None:
        low_chance_reply(update, context)
   

def reply_handler(update, context):
    if update.message.reply_to_message.from_user.is_bot:
        # Reply to bot, so most probably to me! (TODO: Figure out my own ID and use that instead)
        if update.message.reply_to_message.text.startswith("Git käyttäjä "):
            if Bob.objects.get(id=1).global_admin is not None:
                if update.effective_user.id == Bob.objects.get(id=1).global_admin.id:
                    for message_entity in update.message.entities:
                        process_entity(message_entity, update)
                else:
                    update.message.reply_text("Et oo vissiin global_admin? ")
            else:
                update.message.reply_text("Globaalia adminia ei ole asetettu.")


def process_entity(message_entity, update):
    commit_author_email, commit_author_name, git_user = get_git_user_and_commit_info()
    if message_entity.type == "text_mention":
        user = TelegramUser.objects.get(id=message_entity.user.id)
        git_user.tg_user = user
    elif message_entity.type == "mention":
        telegram_users = TelegramUser.objects.all()
        print("Tietokanta: " + str(telegram_users))
        username = re.search('@(.*)', update.message.text)
        print("username:" + username.group(1))
        telegram_users = TelegramUser.objects.filter(username=str(username.group(1)).strip())
        print("Count: " + str(telegram_users.count()))

        if telegram_users.count() > 0:
            git_user.tg_user = telegram_users[0]
        else:
            update.message.reply_text("En löytänyt tietokannastani ketään tuon nimistä. ")
    promote_or_praise(git_user, update.message.bot)
    git_user.save()


def leet_command(update: Update, context: CallbackContext):
    now = datetime.datetime.now(pytz.timezone('Europe/Helsinki'))
    chat = Chat.objects.get(id=update.effective_chat.id)
    sender = ChatMember.objects.get(chat=update.effective_chat.id,
                                    tg_user=update.effective_user.id)
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


def space_command(update: Update, context: CallbackContext) -> None:
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


def users_command(update: Update, context: CallbackContext):
    chat_members = ChatMember.objects.filter(chat=update.effective_chat.id)
    reply_text = ""
    for chat_member in chat_members:
        reply_text += str(chat_member) + ";" + \
                      str(chat_member.rank) + ";" + \
                      str(chat_member.prestige) + ";" + \
                      str(chat_member.message_count) + "\n"
    update.message.reply_text(reply_text, quote=False)


def broadcast_toggle_command(update, context):
    chat = Chat.objects.get(id=update.effective_chat.id)
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


def broadcast_command(update, context):
    message = update.message.text
    broadcast(update.bot, message)


def time_command(update: Update, context: CallbackContext):
    date_time_obj = date_time_obj = datetime.datetime.now(pytz.timezone('Europe/Helsinki')).strftime('%H:%M:%S.%f')[:-4]
    time_stamps_str = str(date_time_obj)
    reply_text = '\U0001F551 ' + time_stamps_str
    update.message.reply_text(reply_text, quote=False)


def weather_command(update, context):
    city = update.message.text.replace("/weather", "").lstrip()
    open_weather_api_key = settings_data.get("open_weather_api_key", "")
    base_url = "https://api.openweathermap.org/data/2.5/weather?"
    city_name = city
    complete_url = base_url + "appid=" + open_weather_api_key + "&q=" + city_name
    if city != "":
        response = requests.get(complete_url)
        x = response.json()
        if x["cod"] != "404":
            y = x["main"]
            current_temperature = round(y["temp"] - 273.15, 1) #kelvin to celsius
            current_pressure = y["pressure"]
            current_humidity = y["humidity"]
            z = x["weather"]
            weather_description = replace_weather_description_with_emojis(z[0]["description"])
            weather_string = ("Sää paikassa " + city_name + ":" +
                "\nLämpötila °C = " +
                            str(current_temperature) +
                "\nIlmanpaine hPa = " +
                            str(current_pressure) +
                "\nIlmankosteus % = " +
                            str(current_humidity) +
                "\nSään kuvaus = " +
                            str(weather_description))
            reply_text = weather_string
        else:
            reply_text = "Kaupunkia ei löydy."
    else:
        reply_text = "Määrittele kaupunki kirjoittamalla se komennon perään."
    update.message.reply_text(reply_text, quote=False)
    
def replace_weather_description_with_emojis(description):
    dictionary_of_weather_emojis= {
        'snow':'\U0001F328',
        'rain': '\U0001F327',
        'fog':'\U0001F32B',
        'smoke':'\U0001F32B',
        'mist':'\U0001F32B',
        'clear sky':'\U0001F31E',	
        'thunderstorm':'\U0001F329',
        'clouds':'\U00002601'
    }
    for i, j in dictionary_of_weather_emojis.items():
        description = description.replace(i,j) 
    return description

def low_chance_reply(update, context):
    random_int = random.randint(1,10000)
    if random_int == 1:
        reply_text = "Vaikuttaa siltä että te olette todella onnekas " + "\U0001F340" # clover emoji
        update.message.reply_text(reply_text, quote=True)


def broadcast(bot, message):
    if message is not None and message != "":
        chats = Chat.objects.all()
        for chat in chats:
            if chat.broadcast_enabled:
                bot.sendMessage(chat.id, message)


def broadcast_and_promote(updater):
    try:
        bob_db_object = Bob.objects.get(id=1)
    except Bob.DoesNotExist:
        bob_db_object = Bob(id=1, uptime_started_date=datetime.datetime.now())
    broadcast_message = os.getenv("COMMIT_MESSAGE")
    if broadcast_message != bob_db_object.latest_startup_broadcast_message:
        broadcast(updater.bot, broadcast_message)
        bob_db_object.latest_startup_broadcast_message = broadcast_message
        promote_committer_or_find_out_who_he_is(updater)
    else:
        broadcast(updater.bot, "Olin vain hiljaa hetken. ")
    bob_db_object.save()


def promote_committer_or_find_out_who_he_is(updater):
    commit_author_email, commit_author_name, git_user = get_git_user_and_commit_info()

    if git_user.tg_user is not None:
        promote_or_praise(git_user, updater.bot)
    else:
        reply_message = "Git käyttäjä " + str(commit_author_name) + " " + str(commit_author_email) + \
            " ei ole minulle tuttu. Onko hän joku tästä ryhmästä?"
        broadcast(updater.bot, reply_message)


def get_git_user_and_commit_info():
    commit_author_name = os.getenv("COMMIT_AUTHOR_NAME")
    commit_author_email = os.getenv("COMMIT_AUTHOR_EMAIL")
    if not GitUser.objects.filter(name=commit_author_name, email=commit_author_email).count() > 0:
        git_user = GitUser(name=commit_author_name, email=commit_author_email)
        git_user.save()
    else:
        git_user = GitUser.objects.get(name=commit_author_name, email=commit_author_email)
    return commit_author_email, commit_author_name, git_user


def promote_or_praise(git_user, bot):
    now = datetime.datetime.now(pytz.timezone('Europe/Helsinki'))
    if git_user.tg_user.latest_promotion_from_git_commit is None or \
       git_user.tg_user.latest_promotion_from_git_commit < now.date() - datetime.timedelta(days=7):
        committer_chat_memberships = ChatMember.objects.filter(tg_user=git_user.tg_user)
        for membership in committer_chat_memberships:
            promote(membership)
        broadcast(bot, str(git_user.tg_user) + " ansaitsi ylennyksen ahkeralla työllä. ")
        git_user.tg_user.latest_promotion_from_git_commit = now.date()
        git_user.tg_user.save()
    else:
        # It has not been week yet since last promotion
        broadcast(bot, "Kiitos " + str(git_user.tg_user) + ", hyvää työtä!")


def update_chat_in_db(update):
    # Check if the chat exists alredy or not in the database:
    if not Chat.objects.filter(id=update.effective_chat.id).count() > 0:
        chat = Chat(id=update.effective_chat.id)
        if int(update.effective_chat.id) < 0:
            chat.title = update.effective_chat.title
        chat.save()


def update_user_in_db(update):
    # TelegramUser
    updated_user = TelegramUser(id=update.effective_user.id)
    if update.effective_user.first_name is not None:
        updated_user.firstName = update.effective_user.first_name
    if update.effective_user.last_name is not None:
        updated_user.lastName = update.effective_user.last_name
    if update.effective_user.username is not None:
        updated_user.username = update.effective_user.username
    updated_user.save()

    # ChatMember
    chat_members = ChatMember.objects.filter(chat=update.effective_chat.id,
                                             tg_user=update.effective_user.id)
    # The relation between tg user and chat
    # The relation between tg user and chat
    if chat_members.count() <= 0:
        chat_member = ChatMember(chat=Chat.objects.get(id=update.effective_chat.id),
                                 tg_user=TelegramUser.objects.get(id=update.effective_user.id),
                                 message_count=1)
    else:
        chat_member = chat_members[0]
        chat_member.message_count += 1
    chat_member.save()


# Reads the ranks.txt and returns it contents as a list
# TODO: make this idempotent
def read_ranks_file():
    file = open('../ranks.txt')
    for line in file:
        # strip removes all whitsespaces from end and beginning
        line = line.strip()
        ranks.append(line)
    file.close()
    return ranks


def init_bot():
    try:
        read_ranks_file()
        with open("../settings.json", mode="r") as data_file:
            json_string = data_file.read()
            settings_data.update(json.loads(json_string))
            token = settings_data["bot_token"]

    except FileNotFoundError:
        print("No token file found...")
        token = "1337:leet"

    # Create the Updater and pass it your bot's token.
    updater = Updater(token)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    # on different commands - answer in Telegram
    dispatcher.add_handler(MessageHandler(Filters.all, message_handler))  # KAIKKI viestit
    # on non command i.e message - echo the message on Telegram
    # dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    broadcast_and_promote(updater)
    return updater


def main() -> None:
    updater = init_bot()

    # Start the Bot
    updater.start_polling()
    # updater.bot.sendMessage(chat_id='<user-id>', text='Hello there!')

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()

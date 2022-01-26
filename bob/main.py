#!/usr/bin/env python

import json
import logging
import os
import sys

import pytz
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

sys.path.append('../web')  # needed for sibling import
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
from django.conf import settings
django.setup()
from bobapp.models import Chat, TelegramUser, ChatMember, Bob


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)
ranks = []


def message_handler(update: Update, context: CallbackContext):
    update_chat_in_db(update)
    update_user_in_db(update)
    if update.message.text == "1337":
        leet_command(update, context)
    elif update.message.text == "/space":
        space_command(update, context)
    elif update.message.text == "/users":
        users_command(update, context)
    elif update.message.text.startswith("/kuulutus"):
        broadcast_toggle_command(update, context)


def leet_command(update: Update, context: CallbackContext):
    logger.info("Received 1337 message")
    now = datetime.now(pytz.timezone('Europe/Helsinki'))
    chat = Chat.objects.get(id=update.effective_chat.id)
    sender = ChatMember.objects.get(chat=update.effective_chat.id,
                                    tg_user=update.effective_user.id)
    if chat.latest_leet != now.today() and \
       now.hour == 13 and \
       now.minute == 37:
        chat.latest_leet = now.today()
        chat.save()
        logger.info("Time correct and today's first.")

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
    else:
        #logger.info("Incorrect time or someone was first.")
        if sender.rank > 0:
            sender.rank -= 1
        down = u"\U0001F53D"
        reply_text = "Alokasvirhe! " + str(sender.tg_user) + " alennettiin arvoon " + \
            ranks[sender.rank] + ". " + down
    update.message.reply_text(reply_text, quote=False)
    sender.save()


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
            launch_date = datetime.fromisoformat(launch_date[:-1])
            delta = launch_date - datetime.now()
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
    update.message.reply_text(reply_text)


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


def broadcast(bot, message):
    if message is not None and message != "":
        chats = Chat.objects.all()
        for chat in chats:
            if chat.broadcast_enabled:
                bot.sendMessage(chat.id, message)


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


def main() -> None:
    updater = init_bot()

    # Start the Bot
    updater.start_polling()
    # updater.bot.sendMessage(chat_id='<user-id>', text='Hello there!')

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


def init_bot():
    try:
        read_ranks_file()
        with open("../settings.json", mode="r") as data_file:
            json_string = data_file.read()
            settings_data = json.loads(json_string)
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

    try:
        bob_db_object = Bob.objects.get(id=1)
    except Bob.DoesNotExist:
        bob_db_object = Bob(id=1, uptime_started_date=datetime.now())
    broadcast_message = os.getenv("BROADCAST_MESSAGE")
    if broadcast_message != bob_db_object.latest_startup_broadcast_message:
        broadcast(updater.bot, broadcast_message)
        bob_db_object.latest_startup_broadcast_message = broadcast_message
    else:
        broadcast(updater.bot, "Olin vain hiljaa hetken. ")
    bob_db_object.save()
    return updater


# Reads the ranks.txt and returns it contents as a list
def read_ranks_file():
    file = open('../ranks.txt')
    for line in file:
        # strip removes all whitsespaces from end and beginning
        line = line.strip()
        ranks.append(line)
    file.close()
    return ranks


if __name__ == '__main__':
    main()

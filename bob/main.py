#!/usr/bin/env python

import json
import logging
import os
import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, ForceReply, MessageEntity
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

sys.path.append('../web')  # needed for sibling import
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
from django.conf import settings
django.setup()
from bobapp.models import Chat, TelegramUser, ChatMember


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)


# Define a few command handlers. These usually take the two arguments update and
# context.
def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    update.message.reply_text(
        fr'Heippa {user.mention_markdown_v2()}\!'
    )


def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('Help!')


def echo(update: Update, context: CallbackContext) -> None:
    """Echo the user message."""
    update.message.reply_text(update.message.text)


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
            launch_date = launch_date.strftime('%d.%m.%Y klo %H:%M:%S (Helsinki)')
        reply_text = 'Seuraava SpaceX laukaisu {}:\n{}\n{}\n'.format(name, launch_date, waiting_time)
    except requests.exceptions.RequestException:
        reply_text = 'Ei tietoa seuraavasta lähdöstä :( API ehkä rikki.'

    update.message.reply_text(reply_text)


def message_handler(update: Update, context: CallbackContext):
    update_chat_in_db(update)
    update_user_in_db(update)
    if update.message.text == "/start":
        start(update, context)
    elif update.message.text == "/help":
        help_command(update, context)
    elif update.message.text == "/space":
        space_command(update, context)
    elif update.message.text == "/users":
        users_command(update, context)


def users_command(update: Update, context: CallbackContext):
    chat_members = ChatMember.objects.filter(chat=update.effective_chat.id)
    reply_text = ""
    for chat_member in chat_members:
        reply_text += str(chat_member) + ";" + \
                      str(chat_member.rank) + ";" + \
                      str(chat_member.prestige) + ";" + \
                      str(chat_member.message_count) + "\n"
    update.message.reply_text(reply_text)


def update_chat_in_db(update):
    # Check if the chat exists alredy or not in the database:
    if Chat.objects.filter(id=update.effective_chat.id).count() > 0:
        pass
    else:
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

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


def init_bot():
    try:
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
    return updater


if __name__ == '__main__':
    main()

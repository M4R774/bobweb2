#!/usr/bin/env python
# pylint: disable=C0116,W0613
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.
First, a few handler functions are defined. Then, those functions are passed to
the Dispatcher and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.
Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""
import json
import logging
import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, ForceReply
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

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
    HELSINKI = ZoneInfo('Europe/Helsinki')
    try:
        r = requests.get('https://api.spacexdata.com/v4/launches/next')
        r = r.json()
        name = r.get('name', None)
        launchdate = r.get('date_utc', None)
        if launchdate:
            launchdate = datetime.fromisoformat(launchdate[:-1])
            launchdate = launchdate.astimezone(HELSINKI)
            launchdate = launchdate.strftime('%m.%d.%Y klo %H:%M:%S (Helsinki)')
    except requests.exceptions.RequestException as e:
        reply_text = 'Ei tietoa seuraavasta lähdöstä :( API ehkä rikki.'
    
    reply_text = 'Seuraava SpaceX lähtö {} lähtee {}'.format(name, launchdate)

    update.message.reply_text(reply_text)


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
        with open("settings.json", mode="r") as data_file:
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
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("space", space_command))
    # on non command i.e message - echo the message on Telegram
    # dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    return updater


if __name__ == '__main__':
    main()

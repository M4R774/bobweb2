from telegram.ext import CallbackContext

from command import ChatCommand
from bob.resources.bob_constants import PREFIXES_MATCHER, DEFAULT_TIMEZONE
from telegram import Update
from zoneinfo import ZoneInfo
import requests
import datetime


class SpaceCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='space',
            regex=r'' + PREFIXES_MATCHER + 'space',
            help_text_short=('!space', 'Seuraava laukaisu')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        space_command(update)

    def is_enabled_in(self, chat):
        return chat.space_enabled


def space_command(update: Update) -> None:
    """
    Send a message when the command /space is issued.
    Queries next spacex launch time from public API:
    https://github.com/r-spacex/SpaceX-API
    """
    helsinki_tz = ZoneInfo(DEFAULT_TIMEZONE)
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

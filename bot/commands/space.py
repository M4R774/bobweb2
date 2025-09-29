from aiohttp import ClientResponseError
from telegram.ext import CallbackContext

from bot import async_http
from bot.commands.base_command import BaseCommand, regex_simple_command
from bot.resources.bob_constants import DEFAULT_TIMEZONE
from telegram import Update
from zoneinfo import ZoneInfo
import datetime


class SpaceCommand(BaseCommand):

    def __init__(self):
        super().__init__(
            name='space',
            regex=regex_simple_command('space'),
            help_text_short=('!space', 'Seuraava laukaisu')
        )

    def is_enabled_in(self, chat):
        return chat.space_enabled

    async def handle_update(self, update: Update, context: CallbackContext = None):
        await space_command(update)


#NOSONAR (S3776)
async def space_command(update: Update) -> None:
    """
    Send a message when the command /space is issued.
    Queries next space launch launch time from public API:
    https://thespacedevs.com/llapi
    """
    helsinki_tz = ZoneInfo(DEFAULT_TIMEZONE)
    try:
        content = await async_http.get_json('https://ll.thespacedevs.com/2.2.0/launch/upcoming/?format=json')
        launches = content.get('results', None)
        closest_launch_name = None
        closest_launch_date = None
        if launches:
            for launch in launches:
                launch_date = launch.get('net', None)
                if launch_date:
                    launch_date = datetime.datetime.fromisoformat(launch_date[:-1])
                    delta = launch_date - datetime.datetime.now()
                    name = launch.get('name', None)
                    if name and delta > datetime.timedelta():
                        if (not closest_launch_name and not closest_launch_date) or closest_launch_date > launch_date:
                            closest_launch_name = name
                            closest_launch_date = launch_date

        if closest_launch_name and closest_launch_date:
            delta = closest_launch_date - datetime.datetime.now()
            days, hours, minutes = delta.days, delta.seconds // 3600, delta.seconds // 60 % 60
            waiting_time = "T-: "
            if days > 0:
                waiting_time += "{} päivää, ".format(days)
            if hours > 0:
                waiting_time += "{} tuntia ja ".format(hours)
            if minutes > 0:
                waiting_time += "{} minuuttia.".format(minutes)
            launch_date = closest_launch_date.astimezone(helsinki_tz).strftime('%d.%m.%Y klo %H:%M:%S (Helsinki)')
            reply_text = 'Seuraava laukaisu on {}\n{}\n{}\n'.format(name, launch_date, waiting_time)
        else:
            reply_text = 'Ei tietoa seuraavasta lähdöstä :( API ehkä muuttunut'
    except ClientResponseError:
        reply_text = 'Ei tietoa seuraavasta lähdöstä :( API ehkä mennyt rikki'

    await update.effective_chat.send_message(reply_text)

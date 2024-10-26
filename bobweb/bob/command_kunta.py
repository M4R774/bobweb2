import asyncio
import logging
import os
import re
import string
import json
import random

import io

from PIL import Image
import folium
from shapely.geometry import shape
from shapely.geometry.multipolygon import MultiPolygon

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import message_board_service
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters

from bobweb.bob.command_image_generation import send_images_response, \
    get_text_in_html_str_italics_between_quotes
from bobweb.bob.openai_api_utils import ResponseGenerationException
from bobweb.bob.utils_common import send_bot_is_typing_status_update

logger = logging.getLogger(__name__)


class KuntaCommand(ChatCommand):

    def __init__(self):
        super().__init__(
            name='kunta',
            regex=regex_simple_command_with_parameters('kunta'),
            help_text_short=('!kunta', 'Satunnainen kunta')
        )
        # Thanks to https://github.com/geoharo/Geokml
        # Check if current working directory and import geojson relatively to working directory
        if re.search(r'bobweb[/\\]bob', os.getcwd()) is not None:
            relative_geojson_path = 'resources/Kuntarajat.geojson'
        else:
            relative_geojson_path = 'bobweb/bob/resources/Kuntarajat.geojson'
        self.kuntarajat = json.loads(open(relative_geojson_path).read())['features']

    def is_enabled_in(self, chat):
        return True

    async def handle_update(self, update: Update, context: CallbackContext = None):
        prompt = self.get_parameters(update.effective_message.text)

        kuntarajat = self.kuntarajat
        if prompt:
            prompt = prompt.casefold().capitalize()
            names = [kunta['properties']['Name'] for kunta in kuntarajat]
            if prompt in names:
                kunta = next(kunta for kunta in kuntarajat if kunta['properties']['Name'] == prompt)
            else:
                await update.effective_chat.send_message(f"Kuntaa {prompt} ei löytynyt :(")
                return
        else:
            kunta = random.choice(kuntarajat)  # NOSONAR
        kunta_name = kunta['properties']["Name"]
        kunta_geo = shape(kunta["geometry"])

        notification_text = 'Kunnan generointi aloitettu. Tämä vie 30-60 sekuntia.'
        started_notification = await update.effective_chat.send_message(notification_text)
        await send_bot_is_typing_status_update(update.effective_chat)
        await handle_image_generation_and_reply(update, kunta_name, kunta_geo)

        # Delete notification message from the chat
        await update.effective_chat.delete_message(started_notification.message_id)


async def handle_image_generation_and_reply(update: Update, kunta_name: string, kunta_geo: MultiPolygon) -> None:
    try:
        image_compilation = generate_and_format_result_image(kunta_geo)
        caption = get_text_in_html_str_italics_between_quotes(kunta_name)
        await send_images_response(update, caption, [image_compilation])
    except ResponseGenerationException as e:  # If exception was raised, reply its response_text
        await update.effective_message.reply_text(e.response_text, do_quote=True, parse_mode=ParseMode.HTML)


def generate_and_format_result_image(kunta_geo: MultiPolygon) -> Image:
    m = folium.Map(location=[kunta_geo.centroid.y, kunta_geo.centroid.x])
    folium.GeoJson(kunta_geo).add_to(m)
    m.fit_bounds(m.get_bounds(), padding=(30, 30))
    img_data = m._to_png(5)
    img = Image.open(io.BytesIO(img_data))
    if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
    return img

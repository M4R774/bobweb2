import logging
import string
import json
import random

import io
from PIL import Image
import folium
from shapely.geometry import shape
from shapely.geometry.multipolygon import MultiPolygon

from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER
from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand

from bobweb.bob.command_dallemini import ImageGenerationException, send_image_response

logger = logging.getLogger(__name__)


class KuntaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='kunta',
            regex=r'^' + PREFIXES_MATCHER + r'kunta($|\s)',
            help_text_short=('!kunta', 'Satunnainen kunta')
        )
        # Thanks to https://github.com/geoharo/Geokml
        self.kuntarajat = json.loads(open('bobweb/bob/resources/Kuntarajat.geojson').read())['features']

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.kunta_command(update, context)

    def is_enabled_in(self, chat):
        return True

    def kunta_command(self, update: Update, context: CallbackContext = None) -> None:
        prompt = self.get_parameters(update.effective_message.text)

        kuntarajat = self.kuntarajat
        if prompt:
            prompt = prompt.casefold().capitalize()
            names = [kunta['properties']['Name'] for kunta in kuntarajat]
            if prompt in names:
                kunta = next(kunta for kunta in kuntarajat if kunta['properties']['Name'] == prompt)
            else:
                update.effective_message.reply_text(f"Kuntaa {prompt} ei löytynyt :(", quote=False)
                return
        else:
            kunta = random.choice(kuntarajat)  #NOSONAR
        kunta_name = kunta['properties']["Name"]
        kunta_geo = shape(kunta["geometry"])

        started_notification = update.effective_message.reply_text('Kunnan generointi aloitettu. Tämä vie 30-60 sekuntia.', quote=False)
        handle_image_generation_and_reply(update, kunta_name, kunta_geo)

        # Delete notification message from the chat
        if context is not None:
            context.bot.deleteMessage(chat_id=update.effective_message.chat_id, message_id=started_notification.message_id)


def handle_image_generation_and_reply(update: Update, kunta_name: string, kunta_geo: MultiPolygon) -> None:
    try:
        image_compilation = generate_and_format_result_image(kunta_name, kunta_geo)
        send_image_response(update, kunta_name, image_compilation)

    except ImageGenerationException as e:  # If exception was raised, reply its response_text
        update.effective_message.reply_text(e.response_text, quote=True, parse_mode='Markdown')


def generate_and_format_result_image(prompt: string, kunta_geo: MultiPolygon) -> Image:

    m = folium.Map(location=[kunta_geo.centroid.y, kunta_geo.centroid.x])
    folium.GeoJson(kunta_geo).add_to(m)
    img_data = m._to_png(5)
    img = Image.open(io.BytesIO(img_data))
    if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
    return img

import logging
import string
import random

import io
from PIL import Image

from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER
from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand

logger = logging.getLogger(__name__)


class KuntaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='kunta',
            regex=r'^' + PREFIXES_MATCHER + r'kunta($|\s)',
            help_text_short=('!kunta', 'Satunnainen kunta')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.kunta_command(update, context)

    def is_enabled_in(self, chat):
        return chat.leet_enabled

    def kunta_command(self, update: Update, context: CallbackContext = None) -> None:
        prompt = random.choice(['Hämeenlinna', 'Pihtipudas', 'Riihimäki'])  # NOSONAR

        started_notification = update.effective_message.reply_text('Kunnan generointi aloitettu. Tämä vie 30-60 sekuntia.', quote=False)
        handle_image_generation_and_reply(update, prompt)

        # Delete notification message from the chat
        if context is not None:
            context.bot.deleteMessage(chat_id=update.effective_message.chat_id, message_id=started_notification.message_id)


def handle_image_generation_and_reply(update: Update, prompt: string) -> None:
    try:
        image_compilation = generate_and_format_result_image(prompt)
        send_image_response(update, prompt, image_compilation)

    except ImageGenerationException as e:  # If exception was raised, reply its response_text
        update.effective_message.reply_text(e.response_text, quote=True, parse_mode='Markdown')


def generate_and_format_result_image(prompt: string) -> Image:
    response = Image.open(f"bobweb/bob/resources/municipalities/{prompt}.png")
    if response.mode in ('RGBA', 'P'): response = response.convert('RGB')
    return response


def send_image_response(update: Update, prompt: string, image_compilation: Image) -> None:
    image_bytes = image_to_byte_array(image_compilation)
    caption = '"_' + prompt + '_"'  # between quotes in italic
    update.effective_message.reply_photo(image_bytes, caption, quote=True, parse_mode='Markdown')


def image_to_byte_array(image: Image) -> bytes:
    img_byte_array = io.BytesIO()
    image.save(img_byte_array, format='JPEG')
    img_byte_array = img_byte_array.getvalue()
    return img_byte_array


# Custom Exception for errors caused by image generation
class ImageGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat

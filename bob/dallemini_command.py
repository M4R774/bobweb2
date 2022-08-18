import logging
import re
import string
from typing import List

import requests
import ast
import datetime
import pytz
import io, base64
from PIL import Image

from constants import PREFIXES_MATCHER
from django.utils.text import slugify
from requests import Response
from telegram import Update
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)


def dallemini_command(update: Update, context: CallbackContext = None) -> None:
    prompt = get_given_prompt(update.message.text)

    if prompt is None:
        update.message.reply_text('Anna jokin syöte komennon jälkeen. \'[.!/]prompt [syöte]\'', quote=False)
    else:
        started_notification = update.message.reply_text('Kuvan generointi aloitettu. Tämä vie 30-60 sekuntia.', quote=False)
        handle_image_generation_and_reply(update, prompt)

        # Delete notification message from the chat
        if context is not None:
            context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=started_notification.message_id)


def get_given_prompt(message) -> string:
    matcher = r'(?<=' + PREFIXES_MATCHER + r'dallemini )[\s\S]*'  # promptissa hyväksytään whitespace merkit
    match = re.search(matcher, message)
    return match.group(0) if match is not None else None


def handle_image_generation_and_reply(update: Update, prompt: string) -> None:
    try:
        image_compilation = generate_and_format_result_image(prompt)
        # image_compilation = Image.open('/temp/2022-08-17_1809_dalle_mini_with_prompt_pasta-with-friends.jpeg')
        send_image_response(update, prompt, image_compilation)

    except ImageGenerationException as e:  # If exception was raised, reply its response_text
        update.message.reply_text(e.response_text, quote=True, parse_mode='Markdown')


def generate_and_format_result_image(prompt: string) -> Image:
    response = post_prompt_request_to_api(prompt)
    if response.status_code == 200:
        images = get_images_from_response(response)
        image_compilation = get_3x3_image_compilation(images)
        return image_compilation
    else:
        logger.error(f'DalleMini post-request returned with status code: {response.status_code}')
        raise ImageGenerationException('Kuvan luominen epäonnistui. Lisätietoa Bobin lokeissa.')


def send_image_response(update: Update, prompt: string, image_compilation: Image) -> None:
    image_bytes = image_to_byte_array(image_compilation)
    caption = '"_' + prompt + '_"'  # between quotes in italic
    update.message.reply_photo(image_bytes, caption, quote=True, parse_mode='Markdown')


def post_prompt_request_to_api(prompt: string) -> Response:
    url = 'https://bf.dallemini.ai/generate'
    request_body = {'prompt': prompt}
    headers = {
        'Host': 'bf.dallemini.ai',
        'Origin': 'https://hf.space',
    }
    return requests.post(url, json=request_body, headers=headers)


def get_images_from_response(response: Response) -> List[type(Image)]:
    response_content = ast.literal_eval(response.content.decode('UTF-8'))
    return convert_base64_strings_to_images(response_content['images'])


def convert_base64_strings_to_images(base_64_strings) -> List[type(Image)]:
    images = []
    for base64_str in base_64_strings:
        image = Image.open(io.BytesIO(base64.decodebytes(bytes(base64_str, "utf-8"))))
        images.append(image)
    return images


def get_3x3_image_compilation(images):
    # Assumption: All images are same size
    i_width = images[0].width if images else 0
    i_height = images[0].height if images else 0

    canvas = Image.new('RGB', (i_width * 3, i_height * 3))

    image_rows = split_to_chunks(images, 3)
    for (r_index, r) in enumerate(image_rows):
        for (i_index, i) in enumerate(r):
            x = i_index * i_width
            y = r_index * i_height
            canvas.paste(i, (x, y))
    return canvas


def split_to_chunks(iterable: List, chunk_size: int):
    list_of_chunks = []
    if iterable is None:
        pass
    elif chunk_size <= 0:
        list_of_chunks = iterable
    else:
        for i in range(0, len(iterable), chunk_size):
            list_of_chunks.append(iterable[i:i + chunk_size])
    return list_of_chunks


def get_image_file_name(prompt):
    now = datetime.datetime.now(pytz.timezone('Europe/Helsinki'))
    date_with_time = now.strftime('%Y-%m-%d_%H%M')
    # django.utils.text.slugify() returns a filename and url safe version of a string
    return str(date_with_time) + '_dalle_mini_with_prompt_' + slugify(prompt) + '.jpeg'


def image_to_byte_array(image: Image) -> bytes:
    img_byte_array = io.BytesIO()
    image.save(img_byte_array, format='JPEG')
    img_byte_array = img_byte_array.getvalue()
    return img_byte_array


# Custom Exception for errors caused by image generation
class ImageGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat

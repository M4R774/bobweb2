import os
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

from settings import default_image_temp_location


def dallemini_command(update: Update, context: CallbackContext = None) -> None:
    prompt = get_given_prompt(update.message.text)

    if prompt is None:
        update.message.reply_text('Anna jokin syöte komennon jälkeen. \'[.!/]prompt [syöte]\'', quote=False)
    else:
        started_notification = update.message.reply_text('Kuvan generointi aloitettu. Tämä vie 30-60 sekuntia.', quote=False)
        image_location = generate_result_image(prompt)
        # Delete notification message from the chat
        if context is not None:
            context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=started_notification.message_id)
        send_image_response(update, prompt, image_location)


def get_given_prompt(message) -> string:
    matcher = r'(?<=' + PREFIXES_MATCHER + 'dallemini ).*'
    match = re.search(matcher, message)
    return match.group(0) if match is not None else None


def generate_result_image(prompt: string):
    response = post_prompt_request_to_api(prompt)
    images = get_images_from_response(response)

    image_compilation = get_3x3_image_compilation(images)
    save_location = get_save_location() + get_image_compilation_file_name(prompt)
    image_compilation.save(save_location)
    return save_location


def send_image_response(update: Update, prompt, image_location: string) -> None:
    image = open(image_location, 'rb')
    caption = '"_' + prompt + '_"'  # between quotes in italic
    update.message.reply_photo(image, caption, quote=True, parse_mode='Markdown')
    image.close()


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


def split_to_chunks(iterable, chunk_size):
    list_of_chunks = []
    for i in range(0, len(iterable), chunk_size):
        list_of_chunks.append(iterable[i:i + chunk_size])
    return list_of_chunks


def get_save_location():
    return os.getenv('BOB_BOT_TEMP_LOCATION') or default_image_temp_location


def get_image_compilation_file_name(prompt):
    now = datetime.datetime.now(pytz.timezone('Europe/Helsinki'))
    date_with_time = now.strftime('%Y-%m-%d_%H%M')
    # django.utils.text.slugify() returns a filename and url safe version of a string
    return str(date_with_time) + '_dalle_mini_with_prompt_' + slugify(prompt) + '.jpeg'



import ast
import base64
import io
import logging
from enum import Enum
from typing import List

from PIL import Image
from aiohttp import ClientResponse, FormData

from bobweb.bob import openai_api_utils, async_http, config
from bobweb.bob.utils_common import ChatMessage

logger = logging.getLogger(__name__)


class ImageRequestMode(Enum):
    # Image generation modes. String value is the API-endpoint.
    CREATE = '/v1/images/generations'
    EDIT = '/v1/images/edits'


async def generate_using_openai_api(prompt: str, image_size: str = '1024x1024') -> List[Image.Image]:
    """
    API documentation: https://platform.openai.com/docs/api-reference/images/create
    :param prompt: prompt used for image generation
    :param image_size: str - image resolution (height and width) that is used for generated images
    :return: List of Image objects
    """
    return await _openai_images_api_request(ImageRequestMode.CREATE, prompt, image_size)


async def edit_using_openai_api(prompt: str, message_history: List[ChatMessage], image_size: str = '1024x1024') -> List[Image.Image]:
    """
    API documentation: https://platform.openai.com/docs/api-reference/images/createEdit
    :param prompt: prompt used for image generation
    :param message_history: List of ChatMessage objects that are used for image generation

    :param image_size: str - image resolution (height and width) that is used for generated images
    :return: List of Image objects
    """
    return await _openai_images_api_request(ImageRequestMode.EDIT, prompt, image_size, message_history)


async def _openai_images_api_request(mode: ImageRequestMode,
                                     prompt: str,
                                     image_size: str | None,
                                     message_history: List[ChatMessage] = None) -> List[Image.Image]:
    """
    API documentation: https://platform.openai.com/docs/api-reference/images
    :param mode: create or edit
    :param prompt: prompt used for image generation
    :param image_size: str - image resolution (height and width) that is used for generated images
    :return: List of Image objects
    """
    openai_api_utils.ensure_openai_api_key_set()

    form = FormData()
    form.add_field('model', 'gpt-image-1')
    form.add_field('prompt', prompt)
    form.add_field('n', '1')
    form.add_field('background', 'opaque')  # transparent is also possible now (change JPEG -> PNG)
    form.add_field('moderation', 'low')  # transparent is also possible now (change JPEG -> PNG)
    if image_size:
        form.add_field('size', image_size)

    if message_history:
        for message in message_history:
            for idx, img in enumerate(message.images):
                img.seek(0)
                form.add_field(
                    'image[]',
                    img,
                    filename=f'image_{idx}.png',
                    content_type='image/jpeg'
                )

    url = 'https://api.openai.com' + mode.value
    headers = {'Authorization': 'Bearer ' + config.openai_api_key}

    response: ClientResponse = await async_http.post(url=url, headers=headers, data=form)
    if response.status != 200:
        await openai_api_utils.handle_openai_response_not_ok(
            response=response,
            general_error_response="Kuvan generoiminen epäonnistui.")

    json = await response.json()

    images: List[Image.Image] = []
    for image_object in json['data']:
        base64_str = image_object['b64_json']
        image: Image.Image = convert_base64_string_to_image(base64_str)

        image_size_tuple = tuple(map(int, image_size.split('x')))
        image.thumbnail(image_size_tuple)
        images.append(image)

    return images


def convert_base64_string_to_image(base_64_string: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.decodebytes(bytes(base_64_string, "utf-8"))))

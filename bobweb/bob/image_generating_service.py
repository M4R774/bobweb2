import ast
import base64
import io
import logging
from typing import List

from PIL import Image
from aiohttp import ClientResponse

from bobweb.bob import openai_api_utils, async_http, config

logger = logging.getLogger(__name__)

# dict for getting Openai Dall-e api expected image size string
image_size_int_to_str = {256: '256x256', 512: '512x512', 1024: '1024x1024'}


class ImageGenerationResponse:
    def __init__(self, images: List[Image.Image]):
        self.images = images or []


async def generate_using_openai_api(prompt: str, image_size: int = 1024) -> ImageGenerationResponse:
    """
    API documentation: https://platform.openai.com/docs/api-reference/images/create
    :param prompt: prompt used for image generation
    :param image_size: int - image resolution (height and width) that is used for generated images
    :return: List of Image objects
    """
    openai_api_utils.ensure_openai_api_key_set()

    payload = {
        "model": "gpt-image-1",
        "prompt": prompt,
        "background": "opaque",  # transparent is also possible now (change JPEG -> PNG)
        "moderation": "low",
        "n": 1,
        "size": image_size_int_to_str.get(image_size),  # 256x256, 512x512, or 1024x1024
    }
    url = 'https://api.openai.com/v1/images/generations'
    headers = {'Authorization': 'Bearer ' + config.openai_api_key}

    response: ClientResponse = await async_http.post(url=url, headers=headers, json=payload)
    if response.status != 200:
        await openai_api_utils.handle_openai_response_not_ok(
            response=response,
            general_error_response="Kuvan generoiminen epäonnistui.")

    json = await response.json()

    images = []
    for image_object in json['data']:
        base64_str = image_object['b64_json']
        image = convert_base64_string_to_image(base64_str)

        image.thumbnail((image_size, image_size))
        images.append(image)

    return ImageGenerationResponse(images)


def convert_base64_string_to_image(base_64_string: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.decodebytes(bytes(base_64_string, "utf-8"))))

from enum import Enum

import openai
from io import BytesIO


import logging
from typing import List

import requests
import ast
import io
import base64
from PIL import Image

from requests import Response
from bobweb.bob.utils_common import split_to_chunks

logger = logging.getLogger(__name__)

# Dallemini api base url hosted by Craiyon.com
DALLEMINI_API_BASE_URL = 'https://bf.dallemini.ai/generate'


class ImageGeneratingModel(Enum):
    """
        Supported image generating models:
        - DALLEMINI - dalleminimodel hosted by Craiyon.com
        - DALLE - OpenAI's first Dall-e model using OpenAi's API
        - DALLE2 - OpenAI's Dall-e 2 model using OpenAi's API

        Each model has it's api version as value.
    """
    DALLEMINI = None
    DALLE = 'image-alpha-001',
    DALLE2 = 'image-alpha-002'


class ImageGeneratingService:

    def generate_images(self, prompt: str, model: ImageGeneratingModel) -> List[Image.Image]:
        match model:
            case ImageGeneratingModel.DALLEMINI:
                return self.generate_dallemini(prompt)
            case ImageGeneratingModel.DALLE | ImageGeneratingModel.DALLE2:
                return self.generate_using_openai_api(prompt, model)

    def generate_dallemini(self, prompt: str) -> List[Image.Image]:
        request_body = {'prompt': prompt}
        headers = {
            'Host': 'bf.dallemini.ai',
            'Origin': 'https://hf.space',
        }
        response = requests.post(DALLEMINI_API_BASE_URL, json=request_body, headers=headers)

        if response.status_code == 200:
            images = get_images_from_response(response)
            image_compilation = get_3x3_image_compilation(images)
            return [image_compilation]
        else:
            logger.error(f'DalleMini post-request returned with status code: {response.status_code}')
            raise ImageGenerationException('Kuvan luominen epäonnistui. Lisätietoa Bobin lokeissa.')

    def generate_using_openai_api(self, prompt: str, model: ImageGeneratingModel) -> List[Image.Image]:
        """
        API documentation: https://platform.openai.com/docs/api-reference/images/create
        :param prompt: prompt used for image generation
        :param model: model used for image generation
        :param num_images: number
        :param image_size:
        :return:
        """
        num_images = 1
        default_size = 256
        int_size_to_str = {256: '256x256', 512: '512x512', 1024: '1024x1024'}

        response = openai.Image.create(
            prompt=prompt,
            n=num_images,
            size=int_size_to_str.get(default_size),  # 256x256, 512x512, or 1024x1024
            response_format='b64_json',  # url or b64_json
        )

        images = []
        for openAiObject in response.data:
            base64_str = openAiObject['b64_json']
            image = Image.open(io.BytesIO(base64.decodebytes(bytes(base64_str, "utf-8"))))

            image.thumbnail((default_size, default_size))
            images.append(image)

        return images


# Custom Exception for errors caused by image generation
class ImageGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat


def get_images_from_response(response: Response) -> List[Image.Image]:
    response_content = ast.literal_eval(response.content.decode('UTF-8'))
    return convert_base64_strings_to_images(response_content['images'])


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


def convert_base64_strings_to_images(base_64_strings) -> List[Image.Image]:
    images = []
    for base64_str in base_64_strings:
        image = Image.open(io.BytesIO(base64.decodebytes(bytes(base64_str, "utf-8"))))
        images.append(image)
    return images


# Singleton instance of this service
instance = ImageGeneratingService()

import base64
from enum import Enum

import openai
import requests
from PIL import Image
from io import BytesIO


class ImageGeneratingModel(Enum):
    """
        Supported image generating models:
        - DALLEMINI - dalleminimodel not hosted by Craiyon.com
        - DALLE - OpenAI's first Dall-e model using OpenAi's API
        - DALLE2 - OpenAI's Dall-e 2 model using OpenAi's API

        Each model has it's api version as value.
    """
    DALLEMINI = None
    DALLE = 'image-alpha-001',
    DALLE2 = 'image-alpha-002'


class ImageGeneratingService:
    def __init__(self, api_key):
        self.api_key = api_key

    def generate_images(self, prompt: str, model: ImageGeneratingModel, num_images=1, image_size=512):
        match model:
            case ImageGeneratingModel.DALLEMINI:
                self.generate_dallemini(prompt)
            case ImageGeneratingModel.DALLE | ImageGeneratingModel.DALLE2:
                self.generate_using_openai_api(prompt, model, num_images, image_size)

    def generate_dallemini(self, prompt: str):
        pass # TODO: Implement


    def generate_using_openai_api(self, prompt: str, model: ImageGeneratingModel, num_images=1, image_size=512):
        openai.api_key = self.api_key

        response = openai.Completion.create(
            engine=model.value,
            prompt=prompt,
            max_tokens=2048,
            n=num_images,
            stop=None,
            temperature=0.7,
        )

        images = []
        for choice in response.choices:
            image_url = choice.text.strip()
            if image_url.startswith("data:"):
                image_data = image_url.split(";base64,")[1]
                image = Image.open(BytesIO(base64.b64decode(image_data)))
            else:
                response = requests.get(image_url)
                image = Image.open(BytesIO(response.content))

            image.thumbnail((image_size, image_size))
            images.append(image)

        return images

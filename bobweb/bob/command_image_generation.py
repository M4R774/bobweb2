import logging
import string
from typing import List

import django
import openai
import requests
import ast
import datetime
import io
import base64
from PIL.Image import Image
from django.utils import html
from openai import OpenAIError, InvalidRequestError

from bobweb.bob import image_generating_service, openai_api_utils
from bobweb.bob.image_generating_service import ImageGeneratingModel, ImageGenerationResponse
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api, \
    user_has_permission_to_use_openai_api, ResponseGenerationException
from bobweb.bob.resources.bob_constants import fitz, FILE_NAME_DATE_FORMAT
from django.utils.text import slugify
from requests import Response
from telegram import Update, ParseMode, InputMediaPhoto
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.utils_common import split_to_chunks

logger = logging.getLogger(__name__)


class ImageGenerationBaseCommand(ChatCommand):
    """ Abstract common class for all image generation commands """
    run_async = True  # Should be asynchronous
    model: ImageGeneratingModel = None

    def is_enabled_in(self, chat):
        return True

    def handle_update(self, update: Update, context: CallbackContext = None):
        prompt = self.get_parameters(update.effective_message.text)

        if not prompt:
            update.effective_message.reply_text("Anna jokin syöte komennon jälkeen. '[.!/]prompt [syöte]'", quote=False)
        else:
            started_notification = update.effective_message.reply_text('Kuvan generointi aloitettu. Tämä vie 30-60 sekuntia.', quote=False)
            self.handle_image_generation_and_reply(update, prompt)

            # Delete notification message from the chat
            if context is not None:
                context.bot.deleteMessage(chat_id=update.effective_message.chat_id,
                                          message_id=started_notification.message_id)

    def handle_image_generation_and_reply(self, update: Update, prompt: string) -> None:
        try:
            response: ImageGenerationResponse = image_generating_service.generate_images(prompt, model=self.model)
            additional_text = f'\n\n{response.additional_description}' if response.additional_description else ''
            caption = get_text_in_html_str_italics_between_quotes(prompt) + additional_text
            send_images_response(update, caption, response.images)

        except ResponseGenerationException as e:
            # If exception was raised, reply its response_text
            update.effective_message.reply_text(e.response_text)
        except InvalidRequestError as e:
            if 'rejected' in str(e) and 'safety system' in str(e):
                update.effective_message.reply_text(DalleCommand.safety_system_error_msg)
            else:
                update.effective_message.reply_text(str(e))
        except OpenAIError as e:
            update.effective_message.reply_text(str(e))


class DalleCommand(ImageGenerationBaseCommand):
    """ Command for generating Dall-e image using OpenAi API """
    model: ImageGeneratingModel = ImageGeneratingModel.DALLE2
    safety_system_error_msg = 'OpenAi: Pyyntösi hylättiin turvajärjestelmämme seurauksena. Viestissäsi saattaa olla ' \
                              'tekstiä, joka ei ole sallittu turvajärjestelmämme mukaan.'

    def __init__(self):
        super().__init__(
            name='dalle',
            regex=regex_simple_command_with_parameters('dalle'),
            help_text_short=('!dalle', '[prompt] -> kuva')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        """ Overrides default implementation only to add permission check before it.
            Validates that author of the message has permission to use openai api through bob bot """
        has_permission = openai_api_utils.user_has_permission_to_use_openai_api(update.effective_user.id)
        if not has_permission:
            return notify_message_author_has_no_permission_to_use_api(update)

        super().handle_update(update, context)


class DalleMiniCommand(ImageGenerationBaseCommand):
    """ Command for generating dallemini image hosted by Craiyon.com """

    model: ImageGeneratingModel = ImageGeneratingModel.DALLEMINI

    def __init__(self):
        super().__init__(
            name='dallemini',
            regex=regex_simple_command_with_parameters('dallemini'),
            help_text_short=('!dallemini', '[prompt] -> kuva')
        )


def send_images_response(update: Update, caption: string, images: List[Image]) -> None:
    media_group = []
    for i, image in enumerate(images):
        # Add caption to only first image of the group (this way it is shown on the chat) Each image can have separate
        # label, but for other than the first they are only shown when user opens single image to view
        image_bytes = image_to_byte_array(image)
        img_media = InputMediaPhoto(media=image_bytes, caption=caption, parse_mode=ParseMode.HTML)
        media_group.append(img_media)

    update.effective_message.reply_media_group(media=media_group, quote=True)


def get_text_in_html_str_italics_between_quotes(text: str):
    return f'"<i>{django.utils.html.escape(text)}</i>"'


def get_image_file_name(prompt):
    date_with_time = datetime.datetime.now(fitz).strftime(FILE_NAME_DATE_FORMAT)
    # django.utils.text.slugify() returns a filename and url safe version of a string
    return f'{date_with_time}_dalle_mini_with_prompt_{slugify(prompt)}.jpeg'


def image_to_byte_array(image: Image) -> bytes:
    img_byte_array = io.BytesIO()
    image.save(img_byte_array, format='JPEG')
    img_byte_array = img_byte_array.getvalue()
    return img_byte_array



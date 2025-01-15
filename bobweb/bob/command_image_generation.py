import datetime
import io
import logging
import re
import string
from typing import List, Optional, Tuple

from PIL.Image import Image
from django.utils.text import slugify
from telegram import Update, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

import bobweb
from bobweb.bob import image_generating_service, openai_api_utils
from bobweb.bob import openai_api_utils
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.image_generating_service import ImageGenerationResponse
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api, \
    ResponseGenerationException
from bobweb.bob.resources.bob_constants import fitz, FILE_NAME_DATE_FORMAT, TELEGRAM_MEDIA_MESSAGE_CAPTION_MAX_LENGTH
from bobweb.bob.utils_common import send_bot_is_typing_status_update, html_escape_and_wrap_with_italics_between_quotes

logger = logging.getLogger(__name__)


class DalleCommand(ChatCommand):
    """ Abstract common class for all image generation commands """
    invoke_on_edit = True
    invoke_on_reply = True

    """ Command for generating Dall-e image using OpenAi API """
    command: str = 'dalle'
    regex: str = regex_simple_command_with_parameters(command)

    def __init__(self):
        super().__init__(
            name=DalleCommand.command,
            regex=DalleCommand.regex,
            help_text_short=(f'!{DalleCommand.command}', '[prompt] -> kuva')
        )

    def is_enabled_in(self, chat):
        return True

    async def handle_update(self, update: Update, context: CallbackContext = None):
        # First check if user has permission to use dalle command
        has_permission = openai_api_utils.user_has_permission_to_use_openai_api(update.effective_user.id)
        if not has_permission:
            return await notify_message_author_has_no_permission_to_use_api(update)

        prompt = self.get_parameters(update.effective_message.text)

        # If there is no prompt in the message with command, but it is a reply to another
        # message, use the reply target message as prompt
        if not prompt and update.effective_message.reply_to_message:
            prompt = bobweb.bob.openai_api_utils.remove_openai_related_command_text_and_extra_info(
                update.effective_message.reply_to_message.text)

        if not prompt:
            await update.effective_chat.send_message("Anna jokin syöte komennon jälkeen. '[.!/]prompt [syöte]'")
        else:
            notification_text = 'Kuvan generointi aloitettu. Tämä vie 30-60 sekuntia.'
            started_notification = await update.effective_chat.send_message(notification_text)
            await send_bot_is_typing_status_update(update.effective_chat)
            await handle_image_generation_and_reply(update, prompt)

            # Delete notification message from the chat
            await update.effective_chat.delete_message(started_notification.message_id)


async def handle_image_generation_and_reply(update: Update, prompt: string) -> None:
    try:
        response: ImageGenerationResponse = await image_generating_service.generate_using_openai_api(prompt)
        caption = get_text_in_html_str_expandable_quote(response.revised_prompt)
        await send_images_response(update, caption, response.images)

    except ResponseGenerationException as e:
        await update.effective_message.reply_text(e.response_text)


async def send_images_response(update: Update, caption: string, images: List[Image]) -> Tuple["Message", ...]:
    """
    Sends images as a media group if possible. Adds given caption to each image. If caption is longer
    than maximum caption length, first images are sent without a caption and then caption is sent as a reply
    to the images
    """
    if len(caption) <= TELEGRAM_MEDIA_MESSAGE_CAPTION_MAX_LENGTH:
        caption_included_to_media = caption
        send_caption_as_message = False
    else:
        caption_included_to_media = None
        send_caption_as_message = True

    media_group = []
    for i, image in enumerate(images):
        # Add caption to only first image of the group (this way it is shown on the chat) Each image can have separate
        # label, but for other than the first they are only shown when user opens single image to view
        image_bytes = image_to_byte_array(image)
        img_media = InputMediaPhoto(media=image_bytes, caption=caption_included_to_media, parse_mode=ParseMode.HTML)
        media_group.append(img_media)

    messages_tuple = await update.effective_message.reply_media_group(media=media_group, do_quote=True)

    # if caption was too long to be sent as a media caption, send it as a message replying
    # to the same original command message
    if send_caption_as_message:
        await update.effective_message.reply_text(caption, parse_mode=ParseMode.HTML, do_quote=True)

    return messages_tuple


def get_image_file_name(prompt):
    date_with_time = datetime.datetime.now(fitz).strftime(FILE_NAME_DATE_FORMAT)
    # django.utils.text.slugify() returns a filename and url safe version of a string
    return f'{date_with_time}_dalle_mini_with_prompt_{slugify(prompt)}.jpeg'


def image_to_byte_array(image: Image) -> Optional[bytes]:
    if image is None:
        return None
    img_byte_array = io.BytesIO()
    image.save(img_byte_array, format='JPEG')
    img_byte_array = img_byte_array.getvalue()
    return img_byte_array


def remove_all_dalle_and_dallemini_commands_related_text(text: str) -> str:
    text = re.sub(f'({DalleCommand.regex})', '', text)
    text = re.sub(rf'"<i>', '', text)
    text = re.sub(rf'</i>"', '', text)
    return text.strip()

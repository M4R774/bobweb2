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

import bot
from bot import main, image_generating_service, openai_api_utils, telethon_service
from bot.commands.base_command import BaseCommand, regex_simple_command_with_parameters
from bot.image_generating_service import ImageRequestMode
from bot.openai_api_utils import notify_message_author_has_no_permission_to_use_api
from bot.litellm_utils import ResponseGenerationException
from bot.resources.bob_constants import fitz, FILE_NAME_DATE_FORMAT
from bot.utils_common import send_bot_is_typing_status_update, ChatMessage

logger = logging.getLogger(__name__)


class DalleCommand(BaseCommand):
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

        message_text = self.get_parameters(update.effective_message.text)

        message_has_image_media = update.effective_message.photo is not None and len(update.effective_message.photo) > 0
        if update.effective_message.reply_to_message:
            replied_message_has_image_media = (update.effective_message.reply_to_message.photo is not None
                                               and len(update.effective_message.reply_to_message.photo) > 0)
            replied_message_has_text = update.effective_message.reply_to_message.text is not None
        else:
            replied_message_has_image_media = False
            replied_message_has_text = False

        replied_message_text = None
        if replied_message_has_text:
            replied_message_text = bot.openai_api_utils.remove_openai_related_command_text_and_extra_info(
                update.effective_message.reply_to_message.text)

        message_history: List[ChatMessage] = []
        if message_text and (message_has_image_media or replied_message_has_image_media):
            # Use edit + command message text as prompt + message media and/or replied message media
            mode = ImageRequestMode.EDIT
            prompt_text = message_text
            # Download content of the message with command and possible previous message in the reply chain
            # For edit mode, message limit of 2 is used so that the context only contains the command message
            # with its content and the previous message in the reply chain
            message_history = await telethon_service.form_message_history(update, message_limit=2, image_format=bytes)
        elif message_text:
            # Message with command has other text -> New image with prompt from command message
            mode = ImageRequestMode.CREATE
            prompt_text = message_text
        elif replied_message_text:
            # Message with command has no other text -> New image with prompt from the replied message
            mode = ImageRequestMode.CREATE
            prompt_text = replied_message_text
        else:
            await update.effective_chat.send_message("Anna jokin syöte komennon jälkeen. '[.!/]prompt [syöte]'")
            return

        notification_text = 'Kuvan generointi aloitettu. Tämä vie 30-60 sekuntia.'
        started_notification = await update.effective_chat.send_message(notification_text)
        await send_bot_is_typing_status_update(update.effective_chat)
        await handle_image_generation_and_reply(
            update,
            mode=mode,
            prompt_text=prompt_text,
            message_history=message_history
        )

        # Delete notification message from the chat
        await update.effective_chat.delete_message(started_notification.message_id)


async def handle_image_generation_and_reply(update: Update, mode: ImageRequestMode, prompt_text: string, message_history: List[ChatMessage]) -> None:
    try:
        match mode:
            case ImageRequestMode.CREATE:
                response: List[Image] = await image_generating_service.generate_using_openai_api(prompt_text)
            case ImageRequestMode.EDIT:
                response: List[Image] = await image_generating_service.edit_using_openai_api(prompt_text, message_history)
            case _:
                raise ResponseGenerationException('Attempted to generate image with unknown mode.')

        await send_images_response(update, response)

    except ResponseGenerationException as e:
        await update.effective_message.reply_text(e.response_text)


async def send_images_response(update: Update, images: List[Image]) -> Tuple["Message", ...]:
    """
    Sends images as a media group if possible. Adds given caption to each image. If caption is longer
    than maximum caption length, first images are sent without a caption and then caption is sent as a reply
    to the images
    """
    media_group = []
    for i, image in enumerate(images):
        image_bytes = image_to_byte_array(image)
        img_media = InputMediaPhoto(media=image_bytes, parse_mode=ParseMode.HTML)
        media_group.append(img_media)

    messages_tuple = await update.effective_message.reply_media_group(media=media_group, do_quote=True)

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


def remove_all_dalle_commands_related_text(text: str) -> str:
    text = re.sub(f'({DalleCommand.regex})', '', text)
    text = str.replace('"<i>', '', text)
    text = str.replace('</i>"', '', text)
    return text.strip()

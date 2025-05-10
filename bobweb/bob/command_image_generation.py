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
from telethon.tl.types import Message as TelethonMessage, Chat as TelethonChat

import bobweb
from bobweb.bob import image_generating_service, openai_api_utils, telethon_service
from bobweb.bob import openai_api_utils
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.image_generating_service import ImageGenerationResponse
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api, \
    ResponseGenerationException
from bobweb.bob.resources.bob_constants import fitz, FILE_NAME_DATE_FORMAT
from bobweb.bob.utils_common import send_bot_is_typing_status_update

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
            replied_message_text = bobweb.bob.openai_api_utils.remove_openai_related_command_text_and_extra_info(
                update.effective_message.reply_to_message.text)

        prompt_images = []
        if message_text and (message_has_image_media or replied_message_has_image_media):
            # Use edit + message text + message media and/or replied message media
            mode = 'edit'
            prompt_text = message_text
            prompt_images = await download_all_images_from_reply_thread_oldest_first(update)
        elif message_text:
            # Use create + message text
            mode = 'create'
            prompt_text = message_text
        elif replied_message_text:
            # Use create + replied message text
            mode = 'create'
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
            prompt_images=prompt_images
        )

        # Delete notification message from the chat
        await update.effective_chat.delete_message(started_notification.message_id)


async def download_all_images_from_reply_thread_oldest_first(update: Update) -> List[io.BytesIO]:
    images = []
    chat_id = update.effective_chat.id
    chat = await telethon_service.client.find_chat(chat_id)
    current_message: TelethonMessage = await telethon_service.client.find_message(chat_id=chat_id,
                                                                                    msg_id=update.effective_message.message_id)
    if current_message.media and hasattr(current_message.media, 'photo') and current_message.media.photo:
        current_message_images = await download_all_images_from_message(chat, current_message)
        images.extend(current_message_images)

    # Current message could be a reply to another message that might be replied to another.
    # Iterate through the reply chain and find all messages in it
    next_id = None
    if update.effective_message.reply_to_message:
        next_id = update.effective_message.reply_to_message.message_id

    while next_id is not None:
        replied_message: TelethonMessage = await telethon_service.client.find_message(chat_id=chat_id,
                                                                                      msg_id=next_id)
        if replied_message.media and hasattr(replied_message.media, 'photo') and replied_message.media.photo:
            replied_message_images = await download_all_images_from_message(chat, replied_message)
            images.extend(replied_message_images)
        next_id = replied_message.reply_to.reply_to_msg_id if replied_message.reply_to else None

    images.reverse()
    return images


async def download_all_images_from_message(chat: TelethonChat, message: TelethonMessage) -> List[io.BytesIO]:
    messages = await telethon_service.client.get_all_messages_in_same_media_group(chat, message)
    image_bytes_list = await telethon_service.client.download_all_messages_image_bytes(messages)
    return image_bytes_list


async def handle_image_generation_and_reply(update: Update, mode: string, prompt_text: string, prompt_images: List[io.BytesIO]) -> None:
    try:
        match mode:
            case 'create':
                response: ImageGenerationResponse = await image_generating_service.generate_using_openai_api(prompt_text)
            case 'edit':
                response: ImageGenerationResponse = await image_generating_service.edit_using_openai_api(prompt_text, prompt_images)
            case _:
                raise ResponseGenerationException('Attempted to generate image with unknown mode.')

        await send_images_response(update, response.images)

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
    text = re.sub(rf'"<i>', '', text)
    text = re.sub(rf'</i>"', '', text)
    return text.strip()

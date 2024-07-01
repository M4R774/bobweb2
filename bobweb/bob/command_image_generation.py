import logging
import string
from typing import List, Optional, Tuple

import django
import io
from PIL.Image import Image
from django.utils import html
from telegram.constants import ParseMode

from bobweb.bob.resources.bob_constants import TELEGRAM_MEDIA_MESSAGE_CAPTION_MAX_LENGTH
from telegram import Update, InputMediaPhoto

logger = logging.getLogger(__name__)

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

    messages_tuple = await update.effective_message.reply_media_group(media=media_group, quote=True)

    # if caption was too long to be sent as a media caption, send it as a message replying
    # to the same original command message
    if send_caption_as_message:
        await update.effective_message.reply_text(caption, parse_mode=ParseMode.HTML, quote=True)

    return messages_tuple


def get_text_in_html_str_italics_between_quotes(text: str):
    return f'"<i>{django.utils.html.escape(text)}</i>"'


def image_to_byte_array(image: Image) -> Optional[bytes]:
    if image is None:
        return None
    img_byte_array = io.BytesIO()
    image.save(img_byte_array, format='JPEG')
    img_byte_array = img_byte_array.getvalue()
    return img_byte_array


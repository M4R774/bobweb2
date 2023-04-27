import io
import json
import logging
from typing import Tuple

import openai
import requests
from pydub.audio_segment import AudioSegment
from telegram import Update, Voice, ParseMode, Audio, Video, VideoNote

import os
import openai.error

from bobweb.bob import main, database, openai_api_utils
from bobweb.bob.command_image_generation import get_text_in_html_str_italics_between_quotes
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api
from bobweb.bob.utils_common import dict_search
from bobweb.web.bobapp.models import Chat

logger = logging.getLogger(__name__)


def handle_voice_or_video_note_message(update: Update):
    """
    Handles any voice or video note message sent to a chat. Only processes it, if automatic transcribing is set to be
    on in the chat settings

    Transcribing: Transcribes voice to text using OpenAi's Whisper api. Requires that the user has permission
                  to use the api
    """

    chat: Chat = database.get_chat(update.effective_chat.id)
    if chat.voice_msg_to_text_enabled:
        has_permission = openai_api_utils.user_has_permission_to_use_openai_api(update.effective_user.id)
        if not has_permission:
            return notify_message_author_has_no_permission_to_use_api(update)
        else:
            transcribe_voice(update, update.effective_message.voice)


def transcribe_voice(update: Update, media_meta: Voice | Audio | Video | VideoNote):
    # 1. Get the file metadata and file proxy from Telegram servers
    file_proxy = media_meta.get_file()

    # 2. Create bytebuffer and download the actual file content to the buffer.
    #    Telegram returns voice message files in 'ogg'-format
    with io.BytesIO() as buffer:
        file_proxy.download(out=buffer)
        buffer.seek(0)

        # 3. Convert audio to mp3 if not yet in that format
        original_format = convert_file_extension_to_file_format(get_file_type_extension(file_proxy.file_path))
        if 'mp3' not in original_format:
            buffer, written_bytes = convert_audio_buffer_to_format(buffer, original_format, to_format='mp3')
        else:
            written_bytes = media_meta.file_size

        max_bytes_length = 1024 ** 2 * 25  # 25 MB
        if written_bytes > max_bytes_length:
            reply_text = f'Äänitiedoston koko oli liian suuri.\n' \
                         f'Koko: {get_mb_str(written_bytes)} MB. Sallittu koko: {get_mb_str(max_bytes_length)} MB.'
            update.effective_message.reply_text(reply_text, quote=True)

        # 6. Prepare request parameters and send it to the api endpoint. Http POST-request is used
        #    instead of 'openai' module, as 'openai' module does not support sending byte buffer as is
        url = 'https://api.openai.com/v1/audio/transcriptions'
        headers = {'Authorization': 'Bearer ' + openai.api_key}
        data = {'model': 'whisper-1'}
        files = {'file': (f'{file_proxy.file_id}.mp3', buffer)}

        try:
            response = requests.post(url, headers=headers, data=data, files=files)
        except Exception as e:
            error_handling(update)
            logger.error(e)
            return

    if response.status_code == 200:
        res_dict = dict_search(json.loads(response.text), 'text')
        transcribed_text = get_text_in_html_str_italics_between_quotes(res_dict)
        cost_str = openai_api_utils.state.add_voice_transcription_cost_get_cost_str(media_meta.duration)
        update.effective_message.reply_text(f'{transcribed_text}\n\n{cost_str}', quote=True, parse_mode=ParseMode.HTML)
    else:
        error_handling(update)
        logger.error(f'Openai /v1/audio/transcriptions request returned with status: {response.status_code}. '
                     f'Response text: \'{response.text}\'')


def convert_file_extension_to_file_format(file_extension: str) -> str:
    return (file_extension
            .replace('oga', 'ogg')
            .replace('ogv', 'ogg')
            .replace('ogx', 'ogg')
            .replace('3gp2', '3gp')
            .replace('3g2', '3gp')
            .replace('3gpp', '3gp')
            .replace('3gpp2', '3gp')
            .replace('m4a', 'aac')
            )


def convert_audio_buffer_to_format(buffer: io.BytesIO, from_format: str, to_format: str) -> Tuple[io.BytesIO, int]:
    """
    Return tuple of buffer and written byte count
    :param buffer: buffer that contains original audio file bytes
    :param from_format: original format
    :param to_format: target format
    :return: tuple (buffer, byte count)
    """
    # 1. Create AudioSegment from the byte buffer with format information
    original_version = AudioSegment.from_file(buffer, format=from_format)

    # 2. Reuse buffer and overwrite it with converted wav version to the buffer
    original_version.export(buffer, format=to_format)

    # 3. Check file size limit after conversion. Uploaded audio file can be at most 25 mb in size.
    #    As 'AudioSegment.export()' seeks the buffer to the start we can get buffer size with (0, 2)
    #    which does not copy whole buffer to the memory
    written_bytes = buffer.seek(0, 2)
    buffer.seek(0)  # Seek buffer back to the start
    return buffer, written_bytes


def error_handling(update: Update):
    update.effective_message.reply_text('Median tekstittäminen ei onnistunut ', quote=True)


def get_file_type_extension(filename: str) -> str | None:
    parts = os.path.splitext(filename)
    if parts and len(parts) > 1:
        return parts[1].replace('.', '')
    return None


def format_float_str(value: float, precision: int = 2) -> str:
    return f'{value:.{precision}f}'


def get_mb_str(byte_count: int) -> str:
    return format_float_str(byte_count / (1024 ** 2))

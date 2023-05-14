import io
import json
import logging
import subprocess
from typing import Tuple

import openai
import requests
from pydub.audio_segment import AudioSegment
from pydub.exceptions import CouldntDecodeError
from telegram import Update, Voice, ParseMode, Audio, Video, VideoNote

import os
import openai.error

from bobweb.bob import main, database, openai_api_utils
from bobweb.bob.command_image_generation import get_text_in_html_str_italics_between_quotes
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api
from bobweb.bob.utils_common import dict_search
from bobweb.web.bobapp.models import Chat

logger = logging.getLogger(__name__)

converter_audio_format = 'mp4'  # Default audio format that is used for converted audio file sent to openai api


def is_ffmpeg_available():
    """ Checks if ffmpeg is available in the host system.
        Calls 'ffmpeg --version' ins sub process to check if ffmpeg is available in path.
        Returns true if available """
    try:
        subprocess.check_call(['ffmpeg', '-version'])
        return True  # No error, ffmpeg is available
    except Exception:
        return False  # Error, ffmpeg not available


# Checks if FFMPEG is installed in the system
ffmpeg_available = is_ffmpeg_available()


class TranscribingError(Exception):
    """ Any error raised while handling audio media file or transcribing it """
    def __init__(self, reason: str, additional_log_content: str = None):
        super(TranscribingError, self).__init__()
        self.reason = reason
        self.additional_log_content = additional_log_content


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
            transcribe_and_send_response(update, update.effective_message.voice)


def transcribe_and_send_response(update: Update, media_meta: Voice | Audio | Video | VideoNote):
    """
    "Controller" of media transcribing. Handles invoking transcription call,
    replying with transcription and handling error raised from the process
    """
    try:
        transcription = transcribe_voice(media_meta)
        transcribed_text = get_text_in_html_str_italics_between_quotes(transcription)
        cost_str = openai_api_utils.state.add_voice_transcription_cost_get_cost_str(media_meta.duration)
        response = f'{transcribed_text}\n\n{cost_str}'
    except CouldntDecodeError as e:
        logger.error(e)
        response = 'Ääni-/videotiedoston alkuperäistä tiedostotyyppiä tai sen sisältämää median ' \
                   'koodekkia ei tueta, eikä sitä näin ollen voida tekstittää.'
    except TranscribingError as e:
        logger.error(f'TranscribingError: {e.additional_log_content}')
        response = f'Median tekstittäminen ei onnistunut. {e.reason or ""}'
    except Exception as e:
        logger.error(e)
        response = 'Median tekstittäminen ei onnistunut odottamattoman poikkeuksen johdosta.'
    finally:
        update.effective_message.reply_text(response, quote=True, parse_mode=ParseMode.HTML)


def transcribe_voice(media_meta: Voice | Audio | Video | VideoNote) -> str:
    """
    Downloads, converts and transcribes given Telegram audio or video object.

    NOTE! May raise Exception
    :param media_meta: media, which is transcribed
    :return: transcription of given media
    """

    # 1. Get the file metadata and file proxy from Telegram servers
    file_proxy = media_meta.get_file()

    # 2. Create bytebuffer and download the actual file content to the buffer.
    #    Telegram returns voice message files in 'ogg'-format
    with io.BytesIO() as buffer:
        file_proxy.download(out=buffer)
        buffer.seek(0)

        # 3. Convert audio to mp3 if not yet in that format
        original_format = convert_file_extension_to_file_format(get_file_type_extension(file_proxy.file_path))
        buffer, written_bytes = convert_buffer_content_to_audio(buffer, original_format)

        max_bytes_length = 1024 ** 2 * 25  # 25 MB
        if written_bytes > max_bytes_length:
            reason = f'Äänitiedoston koko oli liian suuri.\n' \
                     f'Koko: {get_mb_str(written_bytes)} MB. Sallittu koko: {get_mb_str(max_bytes_length)} MB.'
            raise TranscribingError(reason)

        # 6. Prepare request parameters and send it to the api endpoint. Http POST-request is used
        #    instead of 'openai' module, as 'openai' module does not support sending byte buffer as is
        url = 'https://api.openai.com/v1/audio/transcriptions'
        headers = {'Authorization': 'Bearer ' + openai.api_key}
        data = {'model': 'whisper-1'}
        files = {'file': (f'{file_proxy.file_id}.{converter_audio_format}', buffer)}

        response = requests.post(url, headers=headers, data=data, files=files)

    if response.status_code == 200:
        # return transcription from the response content json
        return dict_search(json.loads(response.text), 'text')
    else:
        # If response has any other status code than 200 OK, raise error
        reason = f'OpenAI:n api vastasi pyyntöön statuksella {response.status_code}'
        additional_log = f'Openai /v1/audio/transcriptions request returned with status: ' \
                         f'{response.status_code}. Response text: \'{response.text}\''
        raise TranscribingError(reason, additional_log)


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


def convert_buffer_content_to_audio(buffer: io.BytesIO, from_format: str) -> Tuple[io.BytesIO, int]:
    """
    Return tuple of buffer and written byte count.
    More information about bydup in https://github.com/jiaaro/pydub/blob/master/API.markdown

    :param buffer: buffer that contains original audio file bytes
    :param from_format: original format
    :return: tuple (buffer, byte count)
    """
    # 1. Create AudioSegment from the byte buffer with format information
    original_version = AudioSegment.from_file(buffer, format=from_format)

    # 2. Reuse buffer and overwrite it with converted wav version to the buffer
    parameters = ['-vn']  # ffmpeg parameter -vn: no video, only audio
    original_version.export(buffer, format=converter_audio_format, parameters=parameters)

    # 3. Check file size limit after conversion. Uploaded audio file can be at most 25 mb in size.
    #    As 'AudioSegment.export()' seeks the buffer to the start we can get buffer size with (0, 2)
    #    which does not copy whole buffer to the memory
    written_bytes = buffer.seek(0, 2)
    buffer.seek(0)  # Seek buffer back to the start
    return buffer, written_bytes


def get_file_type_extension(filename: str) -> str | None:
    parts = os.path.splitext(filename)
    if parts and len(parts) > 1:
        return parts[1].replace('.', '')
    return None


def format_float_str(value: float, precision: int = 2) -> str:
    return f'{value:.{precision}f}'


def get_mb_str(byte_count: int) -> str:
    return format_float_str(byte_count / (1024 ** 2))

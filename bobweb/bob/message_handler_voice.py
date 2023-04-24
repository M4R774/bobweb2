import io
import json
import logging
from typing import List, Any

import openai
import pydub
import requests
from openai import File, api_requestor, util
from pydub import AudioSegment
from telegram import Update, File as TelegramFile, Voice, ParseMode

import os
import tempfile
import openai.error

from bobweb.bob import database, openai_api_utils
from bobweb.bob.command_image_generation import get_text_in_html_str_italics_between_quotes
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api
from bobweb.bob.utils_common import dict_search
from bobweb.web.bobapp.models import Chat

logger = logging.getLogger(__name__)

def handle_voice_message(update: Update):
    """
    Handles any voice message sent to a chat. Only processes it, if any processing is set on in the chat settings

    Transcribing: Transcribes voice to text using OpenAi's Whisper api. Requires that the user has permission
                  to use the api
    """

    chat: Chat = database.get_chat(update.effective_chat.id)
    if chat.voice_msg_to_text_enabled:
        has_permission = openai_api_utils.user_has_permission_to_use_openai_api(update.effective_user.id)
        if not has_permission:
            return notify_message_author_has_no_permission_to_use_api(update)
        else:
            transcribe_voice_to_text(update)


def transcribe_voice_to_text(update: Update):
    # 1. Get the file metadata and file proxy from Telegram servers
    voice = update.message.voice
    voice_file = voice.get_file()

    # 2. Create bytebuffer and download the actual file content to the buffer.
    #    Telegram returns voice message files in 'ogg'-format
    with io.BytesIO() as buffer:
        voice_file.download(out=buffer)
        buffer.seek(0)

        # 3. Create AudioSegment from the byte buffer
        ogg_version = AudioSegment.from_file(buffer, duration=voice.duration, format='ogg')

        # 4. Reuse buffer and overwrite it with converted wav version to the buffer
        ogg_version.export(buffer, format='wav')
        buffer.seek(0)
        file_name = f'{voice_file.file_id}.wav'

        # 5. Prepare request parameters and send it to the api endpoint. Http POST-request is used
        #    instead of 'openai' module, as 'openai' module does not support sending byte buffer as is
        url = 'https://api.openai.com/v1/audio/transcriptions'
        headers = {'Authorization': 'Bearer ' + openai.api_key}
        data = {'model': 'whisper-1'}
        files = {'file': (file_name, buffer)}

        try:
            response = requests.post(url, headers=headers, data=data, files=files)
        except Exception as e:
            error_handling(update)
            logger.error(e)
            return

    if response.status_code == 200:
        res_dict = dict_search(json.loads(response.text), 'text')
        transcribed_text = get_text_in_html_str_italics_between_quotes(res_dict)
        cost_str = openai_api_utils.state.add_voice_transcription_cost_get_cost_str(voice.duration)
        update.effective_message.reply_text(f'{transcribed_text}\n\n{cost_str}', quote=True, parse_mode=ParseMode.HTML)
    else:
        error_handling(update)
        logger.error(f'Openai /v1/audio/transcriptions request returned with status: {response.status_code}. '
                     f'Response text: \'{response.text}\'')


def error_handling(update: Update):
    update.effective_message.reply_text('Ei onnistunut', quote=True)

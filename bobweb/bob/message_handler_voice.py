import io
import json
from typing import List, Any

import openai
import pydub
import requests
from openai import File, api_requestor, util
from pydub import AudioSegment
from telegram import Update, File as TelegramFile, Voice

import os
import tempfile
import openai.error

from bobweb.bob import database, openai_api_utils
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api
from bobweb.web.bobapp.models import Chat


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
    # get the file object from the update object
    voice = update.message.voice
    voice_file = voice.get_file()
    ogg_buffer = io.BytesIO()
    voice_file.download(out=ogg_buffer)
    ogg_buffer.seek(0)

    ogg_version = AudioSegment.from_file(ogg_buffer, duration=voice.duration, format='ogg')

    wav_buffer = io.BytesIO()
    ogg_version.export(wav_buffer, format='wav')
    wav_buffer.seek(0)
    wav_buffer.name = voice_file.file_id + '_temp.wav'

    # send the request to OpenAI Whisper api endpoint
    url = 'https://api.openai.com/v1/audio/transcriptions'
    headers = {'Authorization': 'Bearer ' + openai.api_key}
    data = {'model': 'whisper-1'}
    files = {'file': (wav_buffer.name, wav_buffer)}

    try:
        response = requests.post(url, headers=headers, data=data, files=files)
    except:
        error_handling(update, ogg_buffer, wav_buffer)
        return

    if response.status_code == 200:
        update.effective_message.reply_text(response.text)
    else:
        error_handling(update, ogg_buffer, wav_buffer)
    print(response.text)


def error_handling(update: Update, ogg_buffer, wav_buffer):
    update.effective_message.reply_text('Ei onnistunut')
    ogg_buffer.close()
    wav_buffer.close()

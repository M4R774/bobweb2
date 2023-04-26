import io
import json
import logging
from typing import List, Any

import openai
import pydub
import requests
from openai import File, api_requestor, util
from pydub import AudioSegment
from telegram import Update, File as TelegramFile, Voice, ParseMode, Audio

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
            transcribe_voice(update, update.effective_message.voice)


def transcribe_voice(update: Update, audio_meta: Voice | Audio):
    # 1. Get the file metadata and file proxy from Telegram servers
    audio_meta = audio_meta or update.effective_message.voice  # Allows overriding which voice file is transcribed
    file_proxy = audio_meta.get_file()

    if isinstance(audio_meta, Voice):
        filetype = 'ogg'
    else:
        filetype = get_file_type_extension(file_proxy.file_path)

    # 2. Create bytebuffer and download the actual file content to the buffer.
    #    Telegram returns voice message files in 'ogg'-format
    with io.BytesIO() as buffer:
        file_proxy.download(out=buffer)
        buffer.seek(0)

        # 3. Create AudioSegment from the byte buffer
        original_version = AudioSegment.from_file(buffer, duration=audio_meta.duration, format=filetype)

        # 4. Reuse buffer and overwrite it with converted wav version to the buffer
        original_version.export(buffer, format='mp3')

        # 5. Check file size limit after conversion. Uploaded audio file can be at most 25 mb in size.
        #    As 'AudioSegment.export()' seeks the buffer to the start we can get buffer size with (0, 2)
        #    which does not copy whole buffer to the memory
        written_bytes = buffer.seek(0, 2)
        max_bytes_length = 1024 ** 2 * 25  # 25 MB
        if written_bytes > max_bytes_length:
            reply_text = f'Äänitiedoston koko oli liian suuri mp3 konversion jälkeen.\n' \
                         f'Koko: {get_mb_str(written_bytes)} MB. Sallittu koko: {get_mb_str(max_bytes_length)} MB.'

            update.effective_message.reply_text(reply_text, quote=True)

        buffer.seek(0)  # Seek buffer to the start

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
        cost_str = openai_api_utils.state.add_voice_transcription_cost_get_cost_str(audio_meta.duration)
        update.effective_message.reply_text(f'{transcribed_text}\n\n{cost_str}', quote=True, parse_mode=ParseMode.HTML)
    else:
        error_handling(update)
        logger.error(f'Openai /v1/audio/transcriptions request returned with status: {response.status_code}. '
                     f'Response text: \'{response.text}\'')


def error_handling(update: Update):
    update.effective_message.reply_text('Ei onnistunut', quote=True)


def get_file_type_extension(filename: str) -> str | None:
    parts = os.path.splitext(filename)
    if parts and len(parts) > 1:
        return parts[1].replace('.', '')
    return None


def format_float_str(value: float, precision: int = 2) -> str:
    return f'{value:.{precision}f}'


def get_mb_str(byte_count: int) -> str:
    return format_float_str(byte_count / (1024 ** 2))


# Buttons labels for paginator skip to start and skipt to end buttons
paginator_skip_to_start_label = '<<'
paginator_skip_to_end_label = '>>'


class ContentPaginationState(ActivityState):
    """
    Generi activity state for any paginated content. Useful for example if message content is longer than Telegrams
    allowed 4096 characters. Indexes start from 0, labels start from 1.
    """
    def __init__(self, pages: List[str], current_page: int = 0):
        super().__init__()
        self.pages = pages
        self.current_page = current_page

    def execute_state(self):
        if len(self.pages) > 1:
            pagination_labels = create_page_labels(len(self.pages), self.current_page)
            buttons = [InlineKeyboardButton(text=label, callback_data=label) for label in pagination_labels]
            markup = InlineKeyboardMarkup([buttons])
            heading = create_page_heading(len(self.pages), self.current_page)
        else:
            markup = None
            heading = ''
        page_content = heading + self.pages[self.current_page]
        self.activity.reply_or_update_host_message(page_content, markup=markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == paginator_skip_to_start_label:
            next_page = 0
        elif response_data == paginator_skip_to_end_label:
            next_page = len(self.pages) - 1
        else:
            next_page = int(response_data.replace('[', '').replace(']', '')) - 1

        self.current_page = next_page
        self.execute_state()


def create_page_labels(total_pages: int, current_page: int, max_buttons: int = 7) -> List[str]:
    """ Creates buttons labels for simple paginator element. Check tests for examples. Works like standard paginator
        element where buttons are shown up to defined max_buttons count. Current page is surrounded '[x]'"""
    if total_pages == 1:
        return ['[1]']

    half_max_buttons = max_buttons // 2
    if current_page - half_max_buttons <= 0:
        start = 0
        end = min(total_pages, max_buttons)
    elif current_page + half_max_buttons >= total_pages:
        end = total_pages
        start = max(0, total_pages - max_buttons)
    else:
        start = current_page - half_max_buttons
        end = start + max_buttons

    # First button is either '1' or '<<' depending on current page and total page count. Same for last button
    first_btn = paginator_skip_to_start_label if start != 0 else str(1)
    last_btn = paginator_skip_to_end_label if end < total_pages else str(total_pages)
    labels = [first_btn] + [str(i + 1) for i in range(start + 1, end - 1)] + [last_btn]
    # As a last thing, add decoration for current page button
    labels[current_page - start] = '[' + str(labels[current_page - start]) + ']'
    return labels


def create_page_heading(total_pages: int, current_page: int) -> str:
    """ Creates page heading. Returns empty string, if only one page"""
    return f'[Sivu ({current_page + 1} / {total_pages})]\n'

from telegram import Update
from telegram.ext import CallbackContext
import aiohttp
from aiohttp import ClientResponseError
import openai
from openai.error import ServiceUnavailableError, RateLimitError

from bobweb.bob import openai_api_utils, async_http
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api, \
    ResponseGenerationException
from bobweb.bob.utils_common import send_bot_is_typing_status_update, object_search


class SpeechError(Exception):
    """ Any error raised while attempting text-to-speech """
    def __init__(self, reason: str, additional_log_content: str = None):
        super(SpeechError, self).__init__()
        self.reason = reason
        self.additional_log_content = additional_log_content


async def speech(update: Update):
    openai_api_utils.ensure_openai_api_key_set()

    url = 'https://api.openai.com/v1/audio/speech'
    headers = {'Authorization': 'Bearer ' + openai.api_key}

    # Create a FormData object to send files
    # https://platform.openai.com/docs/api-reference/audio/createSpeech
    form_data = aiohttp.FormData()
    form_data.add_field('model', 'tts-1')
    form_data.add_field('input', update.effective_message.text)
    form_data.add_field('voice', 'nova')

    try:
        content: dict = await async_http.post_expect_json(url, headers=headers, data=form_data)
        return object_search(content, 'mp3')
    except ClientResponseError as e:
        reason = f'OpenAI:n api vastasi pyyntöön statuksella {e.status}'
        additional_log = f'Openai /v1/audio/transcriptions request returned with status: ' \
                            f'{e.status}. Response text: \'{e.message}\''
        raise SpeechError(reason, additional_log)


class SpeechCommand(ChatCommand):
    invoke_on_edit = True
    invoke_on_reply = True

    def __init__(self):
        super().__init__(
            name='lausu',
            regex=regex_simple_command('lausu'),
            help_text_short=('!lausu', 'lausuu tekstin ääneen')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        """ Checks requirements, if any fail, user is notified. If all are ok, api is called. """
        has_permission = openai_api_utils.user_has_permission_to_use_openai_api(update.effective_user.id)
        target_message = update.effective_message.reply_to_message

        if not has_permission:
            return await notify_message_author_has_no_permission_to_use_api(update)
        elif not target_message:
            reply_text = 'Lausu viesti ääneen vastaamalla siihen komennolla \'\\lausu\''
            return await update.effective_message.reply_text(reply_text)

        await send_bot_is_typing_status_update(update.effective_chat)

        use_quote = True
        try:
            reply = await speech(update)
        except ServiceUnavailableError | RateLimitError as _:
            # Same error both for when service not available or when too many requests
            # have been sent in a short period of time from any chat by users.
            # In case of error, given message is not sent as quote to the original request
            # message. This is done so that they do not affect message reply history.
            use_quote = False
            reply = ('OpenAi:n palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut. '
                    'Ole hyvä ja yritä hetken päästä uudelleen.')
        except ResponseGenerationException as e:  # If exception was raised, reply its response_text
            use_quote = False
            reply = e.response_text
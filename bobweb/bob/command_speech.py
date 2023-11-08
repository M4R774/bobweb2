from telegram import Update
from telegram.ext import CallbackContext
from aiohttp import ClientResponseError
import openai
from openai.error import ServiceUnavailableError, RateLimitError

from bobweb.bob import openai_api_utils, async_http
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api, \
    ResponseGenerationException, remove_openai_related_command_text_and_extra_info
from bobweb.bob.utils_common import send_bot_is_typing_status_update, object_search


class SpeechError(Exception):
    """ Any error raised while attempting text-to-speech """
    def __init__(self, reason: str, additional_log_content: str = None):
        super(SpeechError, self).__init__()
        self.reason = reason
        self.additional_log_content = additional_log_content


async def speech(target_message: str):
    openai_api_utils.ensure_openai_api_key_set()

    url = 'https://api.openai.com/v1/audio/speech'
    headers = {'Authorization': 'Bearer ' + openai.api_key}

    # https://platform.openai.com/docs/api-reference/audio/createSpeech
    json = {
        'model': 'tts-1',
        'input': target_message,
        'voice': 'nova'
    }

    try:
        content: dict = await async_http.post_expect_bytes(url, headers=headers, json=json)
        return content
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

        if target_message:
            cleaned_message = remove_openai_related_command_text_and_extra_info(target_message.text)

        if not has_permission:
            return await notify_message_author_has_no_permission_to_use_api(update)
        elif not (target_message and cleaned_message):
            reply_text = 'Lausu viesti ääneen vastaamalla siihen komennolla \'\\lausu\''
            return await update.effective_message.reply_text(reply_text)

        started_reply_text = 'Lausunta aloitettu. Tämä vie 2-10 sekuntia.'
        started_reply = await update.effective_chat.send_message(started_reply_text)
        await send_bot_is_typing_status_update(update.effective_chat)

        use_quote = True
        title = cleaned_message[:10]
        try:
            reply = await speech(cleaned_message)
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

        if type(reply) is bytes:
            await update.effective_message.reply_audio(reply, quote=use_quote, title=title)
        else:
            await update.effective_message.reply_text(reply, quote=use_quote)

        # Delete notification message from the chat
        if context is not None:
            await context.bot.deleteMessage(chat_id=update.effective_message.chat_id,
                                            message_id=started_reply.message_id)

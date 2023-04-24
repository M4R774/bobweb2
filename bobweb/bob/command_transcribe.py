from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import openai_api_utils
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.message_handler_voice import transcribe_voice_to_text
from bobweb.bob.openai_api_utils import notify_message_author_has_no_permission_to_use_api


class TranscribeCommand(ChatCommand):
    invoke_on_edit = True
    invoke_on_reply = True
    run_async = True  # Should be asynchronous

    def __init__(self):
        super().__init__(
            name='tekstitä',
            regex=regex_simple_command_with_parameters('tekstitä'),
            help_text_short=('!tekstitä', 'tekstittää kohteen ääniviestin')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        """ Checks requirements, if any fail, user is notified. If all are ok, transcribe-function is called """
        has_permission = openai_api_utils.user_has_permission_to_use_openai_api(update.effective_user.id)
        if not has_permission:
            return notify_message_author_has_no_permission_to_use_api(update)
        elif not update.effective_message.reply_to_message:
            update.effective_message.reply_text('Tekstitä ääniviesti vastaamalla siihen komennolla \'\\tekstitä\'')
        elif not update.effective_message.reply_to_message.voice:
            update.effective_message.reply_text('Kohteena oleva viesti ei ole ääniviesti jota voisi tekstittää')
        else:
            # Use this update as the one which the bot replies with.
            # Use voice of the target message as the transcribed voice message
            transcribe_voice_to_text(update, update.effective_message.reply_to_message.voice)

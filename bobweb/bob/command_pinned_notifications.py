from telegram.ext import CallbackContext

from bobweb.bob import pinned_notifications
from bobweb.bob.command import ChatCommand
from bobweb.bob.pinned_notifications import MessageBoard
from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER, fitz
from telegram import Update
import datetime
import pytz

from bobweb.bob.utils_common import has_no
from bobweb.web.bobapp.models import Chat

notification_service = pinned_notifications.instance


class PinnedNotificationsCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='ilmoitusalue',
            regex=r'' + PREFIXES_MATCHER + 'ilmoitusalue',
            help_text_short=('!ilmoitusalue', 'näyttää ilmoituksia')
        )

    def is_enabled_in(self, chat):
        return True

    def handle_update(self, update: Update, context: CallbackContext = None):
        message_board(update, context)


def message_board(update: Update, context: CallbackContext = None):
    chat: Chat = Chat.objects.filter(id=update.effective_chat.id).first()
    if has_no(chat.message_board_msg_id):
        msg = update.effective_message.reply_text('Notifikaatio host_msg', quote=False)
        context.bot.pin_chat_message(update.effective_chat.id, msg.message_id, disable_notification=True)
        chat.message_board_msg_id = msg.message_id
        chat.save()
        new_msg_board = MessageBoard(chat.id, msg.message_id)
        notification_service.boards.append(new_msg_board)




import telegram
from telegram import Update, Message, ReplyMarkup, InlineKeyboardMarkup
from telegram.ext import CallbackContext

# For having type hints without circular dependency error
# More info: https://medium.com/quick-code/python-type-hinting-eliminating-importerror-due-to-circular-imports-265dfb0580f8
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from bobweb.bob.activities.activity_state import ActivityState


# Class for defining an activity started by command
# Activity can has a state that is persisted over multiple of messages or callback queries
#
# Activities have always a state: ActivityState which defines how it handles replies and callback queries
class CommandActivity:
    def __init__(self, host_message: Message, activity_state: 'ActivityState'):
        # Message that "hosts" the activity (is updated when state changes and contains possible inline buttons)
        self.host_message: Message = host_message
        # Starting state of the activity
        self.activity_state: 'ActivityState' = activity_state

    # Handle callback query (mainly from inline buttons)
    def handle_callback(self, update: Update, context: CallbackContext = None):
        self.activity_state.handle_callback(update, context)

    # handle reply to the host update
    def handle_reply(self, update: Update, context: CallbackContext = None):
        update.callback_query.answer()
        self.activity_state.handle_reply(update, context)

    # method through which state can update activity's state to the next one
    def change_state(self, state: 'ActivityState'):
        self.activity_state = state
        self.activity_state.execute_state()

    def update_host_message_content(self, message_text: str, markup: InlineKeyboardMarkup = None):
        if markup is None:
            markup = InlineKeyboardMarkup([[]])
        self.host_message = self.host_message.edit_text(message_text, parse_mode='Markdown')
        self.host_message = self.host_message.edit_reply_markup(markup)

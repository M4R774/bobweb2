from telegram import Update, Message, InlineKeyboardMarkup

# For having type hints without circular dependency error
# More info: https://medium.com/quick-code/python-type-hinting-eliminating-importerror-due-to-circular-imports-265dfb0580f8
from typing import TYPE_CHECKING

from bobweb.bob import command_service

if TYPE_CHECKING:
    from bobweb.bob.activities.activity_state import ActivityState


# Class for defining an activity started by command
# Activity can have a state that is persisted over multiple of messages or callback queries
#
# Activities have always a state: ActivityState which defines how it handles replies and callback queries
class CommandActivity:
    def __init__(self, state: 'ActivityState' = None, host_message: Message = None):
        # Starting state of the activity
        self.state: 'ActivityState' = state
        # Message that "hosts" the activity (is updated when state changes and contains possible inline buttons)
        self.host_message: Message = host_message

    # Handle callback query (inline buttons) or reply to host message
    def delegate_response(self, update: Update):
        if update.callback_query is not None:
            update.callback_query.answer()
            response_data = update.callback_query.data.strip()
        else:
            reply_text = update.effective_message.text.strip()
            response_data = self.state.preprocess_reply_data(reply_text)

        self.state.handle_response(response_data)

    # method through which state can update activity's state to the next one
    def change_state(self, state: 'ActivityState'):
        state.activity = self
        self.state = state
        self.state.execute_state()

    def update_host_message_content(self, message_text: str, markup: InlineKeyboardMarkup = None):
        if markup is None:
            markup = self.host_message.reply_markup
        if message_text is None:
            message_text = self.host_message.text
        self.host_message = self.host_message.edit_text(text=message_text, reply_markup=markup, parse_mode='Markdown')

    def done(self):
        command_service.instance.remove_activity(self)

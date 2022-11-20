# For having type hints without circular dependency error
# More info: https://medium.com/quick-code/python-type-hinting-eliminating-importerror-due-to-circular-imports-265dfb0580f8
from typing import TYPE_CHECKING

from telegram import Update, Message, InlineKeyboardMarkup

from bobweb.bob import command_service
from bobweb.bob.utils_common import has

if TYPE_CHECKING:
    from bobweb.bob.activities.activity_state import ActivityState


# -------- CommandActivity ------------
# - Base Class for any activity that required more than 1 message/command and/or requires saving some data on memory
#   while it's active
#
# - Can have any state that is of type ActivityState (base class of descendant). Activity state is responsible for
#   handling any users' response (button click or reply message). ActivityStates themselves are responsible for updating
#   activity's state based on user's response. For more information, check 'State' design pattern
#
# - There can be 1 activity / users message. ActivityStates are stored in memory in CommandService's instance
class CommandActivity:
    def __init__(self, host_message: Message = None, state: 'ActivityState' = None):
        self.state = None
        # Message that "hosts" the activity (is updated when state changes and contains possible inline buttons)
        self.host_message: Message = host_message
        # Change and execute first state
        if has(state):
            self.change_state(state)

    def delegate_response(self, update: Update):
        # Handle callback query (inline buttons) or reply to host message
        if update.callback_query is not None:
            update.callback_query.answer()  # have to be called
            response_data = update.callback_query.data.strip()  # callback query's data should not need parsing
        else:
            reply_text = update.effective_message.text.strip()
            response_data = self.state.preprocess_reply_data(reply_text)

        if has(response_data):
            self.state.handle_response(response_data)

    def change_state(self, state: 'ActivityState'):
        state.activity = self  # set two-way references
        self.state = state
        self.state.execute_state()

    def update_host_message_content(self, message_text: str = None, markup: InlineKeyboardMarkup = None):
        # If updated message or markup is not given, uses ones that are stored to the activity's host message
        if has(markup) and has(message_text):
            self.host_message.edit_text(text=message_text, reply_markup=markup, parse_mode='Markdown')
        elif has(message_text):
            self.host_message.edit_text(text=message_text, parse_mode='Markdown')
        elif has(markup):
            self.host_message.edit_reply_markup(reply_markup=markup)

    def done(self):
        # When activity is done, remove its markup (if has any) and remove it from the activity storage
        if has(self.host_message) \
                and has(self.host_message.reply_markup) \
                and has(self.host_message.reply_markup.inline_keyboard):
            self.update_host_message_content(markup=InlineKeyboardMarkup([[]]))
        command_service.instance.remove_activity(self)

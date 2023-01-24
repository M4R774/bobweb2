from telegram import Update, Message, InlineKeyboardButton
from telegram.ext import CallbackContext

from bobweb.bob.activities.command_activity import CommandActivity


# Class for defining a state for an CommandActivity
# Defines how a state behaves (State design pattern)
# Base class can be extended for activity specific State base class.
# Howver ActivityStates responsibilities are to:
# - handle initial users message (that started the activity)
# - handle according to state:
#    - replies to activity's host message
#    - callbacks from activity's inline keyboards
# - based on users actions and state create a object of next ActivityState and
#   proceed activity to it
# - when activity is finished or is ended prematurely, call end() method from the activity
#
# Note: All methods are not required to be implemented. Check module daily_question.start_season_states.py.
class ActivityState:
    def __init__(self, activity: 'CommandActivity' = None):
        self.activity = activity

    def execute_state(self):
        # Execute new state when activity's state is changed.
        # Common behavior: Update host message's content and/or inlineKeyboard.
        pass

    def preprocess_reply_data_hook(self, text: str) -> str:
        # Process users reply message to be expected format before it is forwarded to 'handle_response'
        # This is not required step as users input might be used as it is.
        return text

    def handle_response(self, response_data: str, context: CallbackContext = None):
        # Handle response either from users reply to host message or inline keyboard button's callback query
        # Common behavior: Proceed state based on users input or end activity.
        pass


# Inline keyboard constant buttons
cancel_button = InlineKeyboardButton(text='Peruuta ❌', callback_data='/cancel')
back_button = InlineKeyboardButton(text='⬅', callback_data='/back')

import typing

from telegram import Update, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

if typing.TYPE_CHECKING:
    from bobweb.bob.activities.command_activity import CommandActivity


# Class for defining a state for an CommandActivity
# Defines how a state behaves (State design pattern)
# Base class can be extended for activity specific State base class.
# However, ActivityStates responsibilities are to:
# - handle initial users message (that started the activity)
# - handle according to state:
#    - replies to activity's host message
#    - callbacks from activity's inline keyboards
# - based on users actions and state create an object of next ActivityState and
#   proceed activity to it
# - when activity is finished or is ended prematurely, call end() method from the activity
#
class ActivityState:
    def __init__(self, activity: 'CommandActivity' = None):
        self.activity = activity

    async def execute_state(self, **kwargs):
        # Execute new state when activity's state is changed.
        # Common behavior: Update host message's content and/or inlineKeyboard.
        pass

    async def preprocess_reply_data_hook(self, text: str) -> str:
        # Process users reply message to be expected format before it is forwarded to 'handle_response'
        # This is not required step as users input might be used as it is.
        return text

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        # Handle response either from users reply to host message or inline keyboard button's callback query
        # Common behavior: Proceed state based on users input or end activity.
        pass

    async def send_or_update_host_message(self,
                                          text: str = None,
                                          markup: InlineKeyboardMarkup = None,
                                          parse_mode: ParseMode = None,
                                          photo: bytes = None,
                                          reply_to_message_id: int = None,  # Only affects when sending new message
                                          **kwargs):
        await self.activity.send_or_update_host_message(text, markup, parse_mode, photo, reply_to_message_id, **kwargs)

    def get_chat_id(self) -> int | None:
        """ Returns chat id for this activity. Returns None, if new or orphan state without activity """
        return self.activity.initial_update.effective_chat.id


# Inline keyboard constant buttons
cancel_button = InlineKeyboardButton(text='Peruuta ❌', callback_data='/cancel')
back_button = InlineKeyboardButton(text='⬅', callback_data='/back')

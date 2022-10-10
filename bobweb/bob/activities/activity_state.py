from telegram import Update, Message
from telegram.ext import CallbackContext

from bobweb.bob.activities.command_activity import CommandActivity


# Class for defining a state for a activity
# Defines how a state behaves
# - initial message
# - replies to activity's host update
# - callbacks from activity's inline keyboards
class ActivityState:
    def __init__(self, activity: 'CommandActivity' = None):
        self.activity = activity

    def update_message(self, host_message: Message):
        pass

    def handle_callback(self, update: Update, context: CallbackContext):
        pass

    def handle_reply(self, update: Update, context: CallbackContext):
        pass

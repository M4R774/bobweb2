from telegram import Update
from telegram.ext import CallbackContext


# Class for defining a state for a activity
# Defines how a state behaves
# - initial message
# - replies to activity's host update
# - callbacks from activity's inline keyboards
class ActivityState:
    def __init__(self, activity):
        self.activity = activity

    def update_message(self, host_update: Update):
        pass

    def handle_callback(self, update: Update, context: CallbackContext):
        pass

    def handle_reply(self, update: Update, context: CallbackContext):
        pass

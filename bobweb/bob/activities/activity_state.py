from telegram import Update, Message
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
# Note: All methods are not required to be implemented. Check module daily_question.create_season_states.py.
class ActivityState:
    def __init__(self, activity: 'CommandActivity' = None):
        self.activity = activity

    def execute_state(self):
        pass

    def preprocess_reply_data(self, text: str) -> str:
        pass

    def handle_response(self, text: str):
        pass

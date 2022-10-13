from telegram import Message, Update

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity


# Activity for creating a new daily question season. Can be initiated by DailyQuestion command
# or by a message with '#päivänkysymys' when no season is active
class CreateSeasonActivity(CommandActivity):
    def __init__(self,
                 host_message: Message = None,
                 activity_state: ActivityState = None,
                 update_with_dq: Update = None):
        super().__init__(host_message, activity_state)
        self.season_number_input = None
        self.season_start_date_input = None
        self.update_with_dq = update_with_dq

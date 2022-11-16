from telegram import Message, Update

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.utils_common import has
from bobweb.web.bobapp.models import DailyQuestionSeason


# Activity for creating a new daily question season. Can be initiated by DailyQuestion command
# or by a message with '#päivänkysymys' when no season is active
class StartSeasonActivity(CommandActivity):
    def __init__(self,
                 host_message: Message = None,
                 state: ActivityState = None,
                 update_with_dq: Update = None):
        super().__init__(host_message, state)
        self.season_name_input = None
        self.season_start_date_input = None
        self.update_with_dq = update_with_dq
        self.previous_season: DailyQuestionSeason | None = None

    def get_chat_id(self):
        if has(self.host_message):
            return self.host_message.chat_id
        if has(self.update_with_dq):
            return self.update_with_dq.effective_chat.id

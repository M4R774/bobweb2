from typing import List, TYPE_CHECKING

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command.command_base import ChatCommand
from bobweb.bob.command.aika_command import AikaCommand
from bobweb.bob.command.dallemini_command import DalleMiniCommand
from bobweb.bob.command.help_command import HelpCommand
from bobweb.bob.command.huutista_command import HuutistaCommand
from bobweb.bob.command.kunta_command import KuntaCommand
from bobweb.bob.command.kuulutus_command import KuulutusCommand
from bobweb.bob.command.leet_command import LeetCommand
from bobweb.bob.command.or_command import OrCommand
from bobweb.bob.command.rules_of_acquisition_command import RulesOfAquisitionCommand
from bobweb.bob.command.ruoka_command import RuokaCommand
from bobweb.bob.command.space_command import SpaceCommand
from bobweb.bob.command.users_command import UsersCommand
from bobweb.bob.command.weather_command import WeatherCommand
from bobweb.bob.command.daily_question_command import DailyQuestionHandler, DailyQuestionCommand, MarkAnswerCommand
from bobweb.bob.utils_common import has

if TYPE_CHECKING:
    from bobweb.bob.activities.command_activity import CommandActivity


# Command Service that creates and stores all commands on initialization and all active CommandActivities
# is initialized below on first module import. To get instance, import it from below
class CommandService:
    commands: List[ChatCommand] = []
    current_activities: List['CommandActivity'] = []

    def __init__(self):
        self.create_command_objects()

    def reply_and_callback_query_handler(self, update: Update, context: CallbackContext = None):
        if has(update.callback_query):
            target = update.effective_message
        else:
            target = update.effective_message.reply_to_message

        target_activity = self.get_activity_by_message_and_chat_id(target.message_id, target.chat_id)
        if target_activity is not None:
            target_activity.delegate_response(update, context)

    def add_activity(self, activity: 'CommandActivity'):
        self.current_activities.append(activity)

    def remove_activity(self, activity: 'CommandActivity'):
        self.current_activities.remove(activity)

    def get_activity_by_message_and_chat_id(self, message_id: int, chat_id: int) -> 'CommandActivity':
        for activity in self.current_activities:
            if activity.host_message.message_id == message_id and activity.host_message.chat_id == chat_id:
                return activity

    def create_command_objects(self):
        # 1. Define all commands (except help, as it is dependent on the others)
        # 2. Return list of all commands with helpCommand added
        commands_without_help = self.create_all_but_help_command()
        help_command = HelpCommand(commands_without_help)
        self.commands = commands_without_help + [help_command]

    def create_all_but_help_command(self) -> List[ChatCommand]:
        return [
            LeetCommand(),
            UsersCommand(),
            RuokaCommand(),
            SpaceCommand(),
            KuntaCommand(),
            KuulutusCommand(),
            AikaCommand(),
            RulesOfAquisitionCommand(),
            WeatherCommand(),
            DalleMiniCommand(),
            OrCommand(),
            HuutistaCommand(),
            DailyQuestionHandler(),
            DailyQuestionCommand(),
            MarkAnswerCommand()
        ]


#
# singleton instance of command service
#
instance = CommandService()

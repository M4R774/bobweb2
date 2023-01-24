from typing import List

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_aika import AikaCommand
from bobweb.bob.command_dallemini import DalleMiniCommand
from bobweb.bob.command_help import HelpCommand
from bobweb.bob.command_huutista import HuutistaCommand
from bobweb.bob.command_kunta import KuntaCommand
from bobweb.bob.command_leet import LeetCommand
from bobweb.bob.command_or import OrCommand
from bobweb.bob.command_rules_of_acquisition import RulesOfAquisitionCommand
from bobweb.bob.command_ruoka import RuokaCommand
from bobweb.bob.command_settings import SettingsCommand
from bobweb.bob.command_space import SpaceCommand
from bobweb.bob.command_users import UsersCommand
from bobweb.bob.command_weather import WeatherCommand
from bobweb.bob.command_daily_question import DailyQuestionHandler, DailyQuestionCommand, MarkAnswerCommand
from bobweb.bob.utils_common import has


# Command Service that creates and stores all commands on initialization and all active CommandActivities
# is initialized below on first module import. To get instance, import it from below
class CommandService:
    commands: List[ChatCommand] = []
    current_activities: List[CommandActivity] = []

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

    def add_activity(self, activity: CommandActivity):
        self.current_activities.append(activity)

    def remove_activity(self, activity: CommandActivity):
        self.current_activities.remove(activity)

    def get_activity_by_message_and_chat_id(self, message_id: int, chat_id: int) -> CommandActivity:
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
            AikaCommand(),
            RulesOfAquisitionCommand(),
            WeatherCommand(),
            DalleMiniCommand(),
            OrCommand(),
            HuutistaCommand(),
            DailyQuestionHandler(),
            DailyQuestionCommand(),
            MarkAnswerCommand(),
            SettingsCommand()
        ]


#
# singleton instance of command service
#
instance = CommandService()

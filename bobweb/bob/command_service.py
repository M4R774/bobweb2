from datetime import datetime
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.command import ChatCommand
from bobweb.bob.command_aika import AikaCommand
from bobweb.bob.command_dallemini import DalleMiniCommand
from bobweb.bob.command_help import HelpCommand
from bobweb.bob.command_huutista import HuutistaCommand
from bobweb.bob.command_kuulutus import KuulutusCommand
from bobweb.bob.command_leet import LeetCommand
from bobweb.bob.command_or import OrCommand
from bobweb.bob.command_rules_of_acquisition import RulesOfAquisitionCommand
from bobweb.bob.command_ruoka import RuokaCommand
from bobweb.bob.command_space import SpaceCommand
from bobweb.bob.command_users import UsersCommand
from bobweb.bob.command_weather import WeatherCommand
from bobweb.bob.command_daily_question import DailyQuestionCommand, DailyQuestion


# Singleton Command Service that creates and stores all commands on initialization.
# is initialized below on first module import. To get instance, import it from below
class CommandService:
    commands: List[ChatCommand] = []
    current_activities: List[CommandActivity] = []

    def __init__(self):
        self.create_command_objects()

    def callback_query_handler(self, update: Update, context: CallbackContext = None):
        target_activity = self.get_activity_by_update_id(update.callback_query.message.message_id)
        # Tähän virheiden hallinta
        target_activity.handle_callback(update, context)

    def reply_handler(self, update: Update, context: CallbackContext = None):
        target_activity = self.get_activity_by_update_id(update.update_id)
        # Tähän kanssa virheiden hallinta
        target_activity.handle_reply(update, context)

    def add_activity(self, activity: CommandActivity):
        self.current_activities.append(activity)

    def get_activity_by_update_id(self, update_id) -> CommandActivity:
        for activity in self.current_activities:
            if update_id == activity.host_update.update_id:
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
            KuulutusCommand(),
            AikaCommand(),
            RulesOfAquisitionCommand(),
            WeatherCommand(),
            DalleMiniCommand(),
            OrCommand(),
            HuutistaCommand(),
            DailyQuestion(),
            DailyQuestionCommand()
        ]
#
# singleton instance of command service
#
command_service_instance = CommandService()




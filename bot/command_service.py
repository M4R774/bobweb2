import logging
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bot import error_handler
from bot.commands import gpt
from bot.activities.activity_state import ActivityState
from bot.activities.command_activity import CommandActivity
from bot.commands.aika import AikaCommand
from bot.commands.base_command import BaseCommand
from bot.commands.daily_question import DailyQuestionHandler, DailyQuestionCommand, MarkAnswerCommand
from bot.commands.epic_games import EpicGamesOffersCommand
from bot.commands.help import HelpCommand
from bot.commands.huoneilma import HuoneilmaCommand
from bot.commands.huutista import HuutistaCommand
from bot.commands.image_generation import DalleCommand
from bot.commands.ip_address import IpAddressCommand
from bot.commands.kunta import KuntaCommand
from bot.commands.leet import LeetCommand
from bot.commands.message_board import MessageBoardCommand
from bot.commands.or_command import OrCommand
from bot.commands.rules_of_acquisition import RulesOfAquisitionCommand
from bot.commands.ruoka import RuokaCommand
from bot.commands.sahko import SahkoCommand
from bot.commands.settings import SettingsCommand
from bot.commands.space import SpaceCommand
from bot.commands.speech import SpeechCommand
from bot.commands.transcribe import TranscribeCommand
from bot.commands.twitch import TwitchCommand
from bot.commands.users import UsersCommand
from bot.commands.weather import WeatherCommand
from bot.utils_common import has

logger = logging.getLogger(__name__)


# Command Service that creates and stores all commands on initialization and all active CommandActivities
# is initialized below on first module import. To get instance, import it from below
class CommandService:
    commands: List[BaseCommand] = []
    current_activities: List[CommandActivity] = []

    def __init__(self):
        self.create_command_objects()

    async def reply_and_callback_query_handler(self, update: Update, context: CallbackContext = None) -> bool:
        """
        Handler for reply and callback query updates.
        :param update:
        :param context:
        :return: True, if update was handled by this handler. False otherwise.
        """
        if has(update.callback_query):
            target = update.effective_message
        else:
            target = update.effective_message.reply_to_message

        target_activity = self.get_activity_by_message_and_chat_id(target.message_id, target.chat_id)

        if target_activity is not None:
            await target_activity.delegate_response(update, context)
            return True
        elif has(update.callback_query):
            # If the received update has a callback query, it means that the update is an inline keyboard button press.
            # As the ChatActivity state is no longer persisted in the command_service instance, we'll update
            # content of the message that had the pressed button.
            edited_text = 'Toimenpide aikakatkaistu ⌛️ Aloita se uudelleen uudella komennolla.'
            if target.text:
                edited_text = f'{target.text}\n\n{edited_text}'
            await target.edit_text(edited_text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([]))
            return True
        else:
            return False

    async def start_new_activity(self,
                                 initial_update: Update,
                                 context: CallbackContext,
                                 initial_state: ActivityState):
        activity: CommandActivity = CommandActivity(initial_update=initial_update)
        await activity.change_state(initial_state)
        if activity.host_message is not None:  # NOSONAR (S2583) "Host message is set by overridden change_state calls"
            self.current_activities.append(activity)
        else:
            warning_message = ("Started new CommandActivity for which its initial state did not create a host message. "
                               "InitialState: " + str(initial_state.__class__) if initial_state else 'None')
            logger.warning(warning_message)
            await error_handler.send_message_to_error_log_chat(context.bot, warning_message)

    def remove_activity(self, activity: CommandActivity):
        try:
            self.current_activities.remove(activity)
        except ValueError:
            pass  # Not found -> already removed or never added. Nothing to do.

    def get_activity_by_message_and_chat_id(self, message_id: int, chat_id: int) -> Optional[CommandActivity]:
        for activity in self.current_activities:
            host_message = activity.host_message  # message that contains inline keyboard and is interactive
            if host_message and host_message.message_id == message_id and host_message.chat_id == chat_id:
                return activity
        return None  # If no matching activity is found, return None

    def create_command_objects(self):
        # 1. Define all commands (except help, as it is dependent on the others)
        # 2. Return list of all commands with helpCommand added
        commands_without_help = self.create_all_but_help_command()
        help_command = HelpCommand(commands_without_help)
        # Ip-address command is added after HelpCommand is created as
        # it is restricted only to project maintainers
        self.commands = commands_without_help + [help_command, IpAddressCommand()]

    def create_all_but_help_command(self) -> List[BaseCommand]:
        return [
            LeetCommand(),
            UsersCommand(),
            RuokaCommand(),
            SpaceCommand(),
            KuntaCommand(),
            AikaCommand(),
            RulesOfAquisitionCommand(),
            WeatherCommand(),
            DalleCommand(),
            OrCommand(),
            HuutistaCommand(),
            DailyQuestionHandler(),
            DailyQuestionCommand(),
            MarkAnswerCommand(),
            EpicGamesOffersCommand(),
            SettingsCommand(),
            HuoneilmaCommand(),
            SahkoCommand(),
            TranscribeCommand(),
            SpeechCommand(),
            gpt.instance,
            TwitchCommand(),
            MessageBoardCommand()
        ]


#
# singleton instance of command service
#
instance = CommandService()

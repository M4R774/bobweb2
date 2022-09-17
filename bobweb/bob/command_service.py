from types import NoneType
from typing import List
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
from bobweb.bob.command_daily_question import DailyQuestionCommand


# Singleton Command Service that creates and stores all commands on initialization.
class CommandService(object):
    commands: List[ChatCommand] | NoneType = None

    def __new__(cls):
        # First call create commands instances. On subsequent calls, return those.
        if cls.commands is None:
            cls.commands = create_command_objects()

        return cls.commands


def create_command_objects() -> List[ChatCommand]:
    # 1. Define all commands (except help, as it is dependent on the others)
    # 2. Return list of all commands with helpCommand added
    commands_without_help = create_all_but_help_command()
    help_command = HelpCommand(commands_without_help)
    return commands_without_help + [help_command]


def create_all_but_help_command() -> List[ChatCommand]:
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
        DailyQuestionCommand()
    ]

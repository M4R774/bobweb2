from typing import List
from bob.abstract_command import AbstractCommand
from bob.aika_command import AikaCommand
from bob.help_command import HelpCommand
from bob.huutista_command import HuutistaCommand
from bob.kuulutus_command import KuulutusCommand
from bob.leet_command import LeetCommand
from bob.or_command import OrCommand
from bob.rules_of_acquisition_command import RulesOfAquisitionCommand
from bob.ruoka_command import RuokaCommand
from bob.space_command import SpaceCommand
from bob.users_command import UsersCommand
from bob.weather_command import WeatherCommand

# Singleton Command Service that creates and stores all commands on initialization.
class CommandService(object):
    commands: List[AbstractCommand] = None

    def __new__(cls):
        # First call create commands instances. On subsequent calls, return those.
        if cls.commands is None:
            cls.commands = create_command_objects()

        return cls.commands


def create_command_objects() -> List[AbstractCommand]:
    # 1. Define all commands (except help, as it is dependent on the others)
    # 2. Return list of all commands with helpCommand added
    commands_without_help = create_all_but_help_command()
    help_command = HelpCommand(commands_without_help)
    return commands_without_help + [help_command]


def create_all_but_help_command() -> List[AbstractCommand]:
    return [
        LeetCommand(),
        UsersCommand(),
        RuokaCommand(),
        SpaceCommand(),
        KuulutusCommand(),
        AikaCommand(),
        RulesOfAquisitionCommand(),
        WeatherCommand(),
        OrCommand(),
        HuutistaCommand()
    ]

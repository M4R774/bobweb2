from abc import ABC, abstractmethod
import re


class AbstractCommand(ABC):

    # Attributes that all Commands Should have
    def __init__(self, name, regex, help_text_short):
        self.name = name
        self.regex = regex
        self.help_text_short = help_text_short

    @abstractmethod
    def handle_update(self, update) -> None:
        pass

    @abstractmethod
    def is_enabled_in(self, chat) -> bool:
        pass

    def regex_matches(self, message) -> bool:
        return re.search(self.regex, message) is not None

import logging
import random
import rules_of_acquisition

from abstract_command import AbstractCommand
from bob.constants import PREFIXES_MATCHER

logger = logging.getLogger(__name__)


class RulesOfAquisitionCommand(AbstractCommand):
    def __init__(self):
        super().__init__(
            'sääntö',
            r'' + PREFIXES_MATCHER + 'sääntö',
            ('!sääntö', '[nro] Hankinnan sääntö')
        )

    def handle_update(self, update):
        rules_of_acquisition_command(update)

    def is_enabled_in(self, chat):
        return chat.proverb_enabled


def rules_of_acquisition_command(update):
    rule_number = update.message.text.split(" ")[1]
    try:
        update.message.reply_text(rules_of_acquisition.dictionary[int(rule_number)], quote=False)
    except (KeyError, ValueError) as e:
        logger.info("Rule not found with key: \"" + str(e) + "\" Sending random rule instead.")
        random_rule_number = random.choice(list(rules_of_acquisition.dictionary))
        random_rule = rules_of_acquisition.dictionary[random_rule_number]
        update.message.reply_text(str(random_rule_number) + ". " + random_rule, quote=False)

import logging
import random
import re

from telegram import Update
from telegram.ext import CallbackContext

from resources import rules_of_acquisition

from command import ChatCommand
from resources.bob_constants import PREFIXES_MATCHER

logger = logging.getLogger(__name__)


class RulesOfAquisitionCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='sääntö',
            regex=r'^' + PREFIXES_MATCHER + 'sääntö',
            help_text_short=('!sääntö', '[nro]')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.rules_of_acquisition_command(update)

    def is_enabled_in(self, chat):
        return chat.proverb_enabled

    def rules_of_acquisition_command(self, update):
        rule_number = ''.join(re.split(self.regex, update.message.text))
        try:
            update.message.reply_text(rules_of_acquisition.dictionary[int(rule_number)], quote=False)
        except (KeyError, ValueError) as e:
            logger.info("Rule not found with key: \"" + str(e) + "\" Sending random rule instead.")
            random_rule_number = random.choice(list(rules_of_acquisition.dictionary))
            random_rule = rules_of_acquisition.dictionary[random_rule_number]
            update.message.reply_text(str(random_rule_number) + ". " + random_rule, quote=False)

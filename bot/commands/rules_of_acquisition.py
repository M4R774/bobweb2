import asyncio
import logging
import random

from telegram import Update
from telegram.ext import CallbackContext

from bot.resources import rules_of_acquisition

from bot.commands.base_command import BaseCommand, regex_simple_command_with_parameters

logger = logging.getLogger(__name__)


class RulesOfAquisitionCommand(BaseCommand):
    def __init__(self):
        super().__init__(
            name='sääntö',
            regex=regex_simple_command_with_parameters('sääntö'),
            help_text_short=('!sääntö', '[nro]')
        )

    def is_enabled_in(self, chat):
        return chat.proverb_enabled

    async def handle_update(self, update: Update, context: CallbackContext = None):
        rule_number = self.get_parameters(update.effective_message.text)
        try:
            await update.effective_chat.send_message(rules_of_acquisition.rules[int(rule_number)])
        except (KeyError, ValueError) as e:
            logger.info("Rule not found with key: \"" + str(e) + "\" Sending random rule instead.")
            random_rule_number = random.choice(list(rules_of_acquisition.rules))  # NOSONAR
            random_rule = rules_of_acquisition.rules[random_rule_number]
            await update.effective_chat.send_message(str(random_rule_number) + ". " + random_rule)

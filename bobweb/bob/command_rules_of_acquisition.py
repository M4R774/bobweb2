import asyncio
import logging
import random

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.resources import rules_of_acquisition

from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters

logger = logging.getLogger(__name__)


class RulesOfAquisitionCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='sääntö',
            regex=regex_simple_command_with_parameters('sääntö'),
            help_text_short=('!sääntö', '[nro]')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        self.rules_of_acquisition_command(update)

    def is_enabled_in(self, chat):
        return chat.proverb_enabled

    def rules_of_acquisition_command(self, update):
        rule_number = self.get_parameters(update.effective_message.text)
        try:
            coroutine = update.effective_message.reply_text(rules_of_acquisition.dictionary[int(rule_number)], quote=False)
        except (KeyError, ValueError) as e:
            logger.info("Rule not found with key: \"" + str(e) + "\" Sending random rule instead.")
            random_rule_number = random.choice(list(rules_of_acquisition.dictionary))  # NOSONAR
            random_rule = rules_of_acquisition.dictionary[random_rule_number]
            coroutine = update.effective_message.reply_text(str(random_rule_number) + ". " + random_rule, quote=False)
        asyncio.create_task(coroutine)

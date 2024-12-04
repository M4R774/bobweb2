import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import telegram
from telegram import Update, Message, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bobweb.bob import command_service, utils_common
from bobweb.bob.utils_common import has, utctz_from, flatten

logger = logging.getLogger(__name__)

# For having type hints without circular dependency error
# More info: https://medium.com/quick-code/python-type-hinting-eliminating-importerror-due-to-circular-imports-265dfb0580f8
if TYPE_CHECKING:
    from bobweb.bob.activities.activity_state import ActivityState


class CommandActivity:
    """
    - Base Class for any activity that required more than 1 message/command and/or requires saving some data on memory
      while it's active

    - Can have any state that is of type ActivityState (base class of descendant). Activity state is responsible for
      handling any users' response (button click or reply message). ActivityStates themselves are responsible for updating
      activity's state based on user's response. For more information, check 'State' design pattern

    - There can be 1 activity / users message. ActivityStates are stored in memory in CommandService's instance
    """

    def __init__(self, initial_update=None, host_message: Message = None):
        self.state: Optional['ActivityState'] = None
        # Initial update (that initiated this activity)
        self.initial_update: Update = initial_update
        # Message that "hosts" the activity (is updated when state changes and contains possible inline buttons)
        self.host_message: Message = host_message

    async def start_with_state(self, state: 'ActivityState'):
        # Change and execute first state
        if has(state):
            await self.change_state(state)

    async def delegate_response(self, update: Update, context: CallbackContext = None):
        # Handle callback query (inline buttons) or reply to host message
        if update.callback_query:
            response_data = update.callback_query.data  # callback query's data should not need parsing
        else:
            reply_text = update.effective_message.text.strip()
            response_data = await self.state.preprocess_reply_data_hook(reply_text)

        if has(response_data):
            await self.state.handle_response(update=update, response_data=response_data, context=context)

        # As a last step confirm that the callback_query has been received
        if update.callback_query:
            await update.callback_query.answer()  # have to be called

    async def change_state(self, state: 'ActivityState'):
        state.activity = self  # set two-way references
        self.state = state
        await self.state.execute_state()

    async def send_or_update_host_message(self,
                                          text: str = None,
                                          markup: InlineKeyboardMarkup = None,
                                          parse_mode: ParseMode = None,
                                          photo: bytes = None,
                                          reply_to_message_id: int = None,  # Only affects when sending new message
                                          **kwargs):
        """
        Important! All user variable values that can contain markdown or html syntax character should be escaped when
        contained inside a message with markdown or html parse_mode. However, when using markdown v1, elements cannot be
        nested meaning that no escape is required inside another element definition. To escape MarkDown text use
        'escape_markdown' from package 'telegram.utils.helpers'. For html use 'escape' from django.utils.html
        For more information, check: https://core.telegram.org/bots/api#markdown-style
        """
        if self.host_message is None:  # If first update and no host message is yet saved
            self.host_message = await self.__new_message(text, parse_mode, markup, photo, reply_to_message_id, **kwargs)
        else:
            try:
                self.host_message = await self.__update(text, parse_mode, markup, photo, **kwargs)
            except telegram.error.BadRequest as error:
                if 'not modified' in error.message.lower():
                    logger.warning('Tried to update message, but Telegram responded with "Message is not modified" '
                                   'error. Check implementation. This is not critical and as such is ignored. '
                                   'Called from: ' + str(utils_common.get_caller_from_stack()))
                else:
                    raise error

    async def done(self):
        # When activity is done, remove its keyboard markup (if it has any) and remove it from the activity storage
        if len(self.__find_current_keyboard()) > 0:
            await self.send_or_update_host_message(markup=InlineKeyboardMarkup([]))
        command_service.instance.remove_activity(self)

    #
    # Lower abstraction implementation details
    #

    def get_chat_id(self):
        if has(self.host_message):
            return self.host_message.chat_id
        if has(self.initial_update):
            return self.initial_update.effective_chat.id

    async def __new_message(self, text: str,
                            parse_mode: ParseMode,
                            markup: InlineKeyboardMarkup,
                            image: bytes = None,
                            reply_to_message_id: int = None,
                            **kwargs) -> Message:
        if image:
            return await self.initial_update.effective_chat.send_photo(
                photo=image, caption=text, parse_mode=parse_mode, reply_markup=markup,
                reply_to_message_id=reply_to_message_id)
        else:

            return await self.initial_update.effective_chat.send_message(
                text=text, parse_mode=parse_mode, reply_markup=markup,
                reply_to_message_id=reply_to_message_id, **kwargs)

    async def __update(self,
                       new_text: str,
                       parse_mode: ParseMode,
                       markup: InlineKeyboardMarkup,
                       image: Optional[bytes] = None, **kwargs) -> Message:
        """
        Updates the message that "hosts" the activity.
        :param new_text: new text that is updated. If None is given, text is not updated. To explicitly remove text use
                         empty string
        :param parse_mode: new parse mode
        :param markup: new markup. To remove markup buttons use 'InlineKeyboardMarkup([])'
        :param image: new image. If None is given, image is not updated
        :param kwargs: key-word arguments that are passed to the update method IF updating normal text message.
        :return: the updated message
        """
        if new_text is None:
            new_text = self.host_message.text or self.host_message.caption

        if self.host_message.photo:
            # If new image is given as an argument, it is updated. Otherwise, only the caption (message text) is updated
            if image:
                new_message = InputMediaPhoto(media=image, caption=new_text, parse_mode=parse_mode)
                return await self.host_message.edit_media(media=new_message, reply_markup=markup)
            else:
                return await self.host_message.edit_caption(caption=new_text, reply_markup=markup, parse_mode=parse_mode)

        if new_text == self.host_message.text and markup == self.host_message.reply_markup:
            return self.host_message  # nothing to update

        # If updated message or markup is not given, uses ones that are stored to the activity's host message
        new_text = new_text or self.host_message.text
        new_markup = markup or self.host_message.reply_markup
        return await self.host_message.edit_text(
            new_text, parse_mode=parse_mode, reply_markup=new_markup, **kwargs)

    def __find_current_keyboard(self) -> []:
        try:
            return flatten(self.host_message.reply_markup.inline_keyboard)
        except (NameError, AttributeError):
            return []


# Parses date and returns it. If parameter is not valid date in any predefined format, None is returned
def parse_dt_str_to_utctzstr(text: str) -> str | None:
    for date_format in ('%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y'):  # 2022-01-31, 31.01.2022, 01/31/2022
        try:
            # As only date is relevant, this is handled as Utc datetime with time of 00:00:00
            naive_dt = datetime.strptime(text, date_format)
            utc_transformed_dt = utctz_from(naive_dt)
            return str(utc_transformed_dt)
        except ValueError:
            pass
    return None


date_formats_text = 'Tuetut formaatit ovat \'vvvv-kk-pp\', \'pp.kk.vvvv\' ja \'kk/pp/vvvv\'.'
date_invalid_format_text = f'Antamasi päivämäärä ei ole tuettua muotoa. {date_formats_text}'

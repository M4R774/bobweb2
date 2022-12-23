import datetime
import itertools
import os
from types import NoneType
from typing import Any
from unittest.mock import MagicMock, Mock

import django
import pytz
from telegram import Chat, User, Bot, Update, Message, CallbackQuery, ReplyMarkup
from telegram.ext import CallbackContext

from bobweb.bob import message_handler, command_service
from bobweb.bob.tests_msg_btn_utils import buttons_from_reply_markup, get_callback_data_from_buttons_by_text

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


class MockBot(Mock):  # This is inherited from bot as this Bot class is complicated
    new_id = itertools.count()

    def __init__(self,
                 id: int = next(new_id),
                 username=None):
        super().__init__(
            spec=Bot
        )
        self.id = id
        self.username = username if not None else f'{chr(64 + id + 1)}_bot'
        self.tg_user = Mock()
        self.tg_user.is_bot = True
        self.tg_user.username = self.username

        self.chats: list[MockChat] = []
        self.messages: list[MockMessage] = []

    # Message from bot to the chat
    def send_message(self,
                     text: str,
                     chat_id: int = None,
                     **_kwargs: Any) -> 'MockMessage':
        chat = get_chat(self.chats, chat_id)
        message = MockMessage(bot=self, chat=chat, from_user=self, text=text, **_kwargs)

        # Add message to both users and chats messages
        self.messages.append(message)
        chat.messages.append(message)
        return message

    # Edits own message with given id. If no id is given, edits last sent message.
    def edit_message_text(self, text: str, message_id: int = None, reply_markup=None, **kwargs: Any) -> 'MockMessage':
        if message_id is None:
            message_id = self.messages[-1].message_id
        message = [x for x in self.messages if x.message_id == message_id].pop()
        message.text = text
        message.reply_markup = reply_markup
        return message


# # Multiple bots per not supported at least for now
# bot = MockBot()


class MockChat(Chat):
    id_seq = 0

    def __init__(self,
                 id: int = id_seq + 1,
                 type: str = 'group'):
        super().__init__(
            id=id,
            type=type
        )
        MockChat.id_seq = MockChat.id_seq + 1
        self.title = 'mock_chat'

        self.messages: list[MockMessage] = []
        self.users: list[MockUser] = []
        # bot.chats.append(self)
        self.bot: MockBot = MockBot()
        self.bot.chats.append(self)

    def get_last_bot_msg(self) -> 'MockMessage':
        if len(self.bot.messages) == 0:
            return None
        return self.bot.messages[-1]

    def get_last_user_msg(self) -> 'MockMessage':
        if len(self.messages) == 0:
            return None
        return self.messages[-1]


class MockUser(User):
    new_id = itertools.count(start=1)

    def __init__(self,
                 id: int = None,
                 first_name: str = None,
                 chats: list[MockChat] = None,
                 **_kwargs: Any):
        self.id = id if id is not None else next(MockUser.new_id)
        self.first_name = first_name if first_name is not None else chr(64 + self.id)  # 65 = 'A', 66 = 'B' ...
        self.is_bot = False
        super().__init__(self.id, self.first_name, self.is_bot, **_kwargs)
        self.username = self.first_name
        self.chats: list[MockChat] = chats
        self.messages: list[MockMessage] = []

    # Method for mocking an update that is received by bot's message handler
    def send_update(self,
                    text: str,
                    chat_id: int = None,
                    context: CallbackContext = None,
                    reply_to_message: 'MockMessage' = None) -> 'MockMessage':
        chat = get_chat(self.chats, chat_id)
        message = MockMessage(chat=chat, bot=chat.bot, from_user=self, text=text, reply_to_message=reply_to_message)

        # Add message to both users and chats messages
        self.messages.append(message)
        chat.messages.append(message)

        update = MockUpdate(message=message, effective_user=self)
        message_handler.handle_update(update, context)
        return message

    # Simulates pressing a button from bot's message and sending update with inlineQuery to bot
    def press_button(self, label: str, msg_with_btns=None):
        if msg_with_btns is None:  # Message not given, get last chats last message from bot
            msg_with_btns = self.chats[-1].bot.messages[-1]
        buttons = buttons_from_reply_markup(msg_with_btns.reply_markup)

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.data = get_callback_data_from_buttons_by_text(buttons, label)
        if callback_query.data is None:
            raise Exception('callback_data should not be None. Check that the buttons are as expected')

        update = MockUpdate(callback_query=callback_query, message=msg_with_btns)
        command_service.instance.reply_and_callback_query_handler(update)


# Update = Incoming update from telegram api. Every message and media post is contained in update
class MockUpdate(Update):
    id_seq = 0

    def __init__(self,
                 update_id: int = id_seq + 1,
                 message: 'MockMessage' = None,
                 edited_message: 'MockMessage' = None,
                 effective_user: 'MockUser' = None,
                 **_kwargs: Any):
        effective_message = edited_message if edited_message is not None else message
        super().__init__(
            update_id=update_id,
            message=message,
            edited_message=edited_message,
            effective_message=effective_message,
            _effective_user=effective_user,
            **_kwargs
        )
        MockUpdate.id_seq = MockUpdate.id_seq + 1


# Single message. If received from Telegram API, is inside an update
class MockMessage(Message):
    id_seq = 0

    def __init__(self,
                 chat: MockChat,
                 from_user: MockUser,
                 bot: MockBot = None,
                 message_id: int = id_seq + 1,
                 date: datetime = datetime.datetime.now(tz=pytz.UTC),
                 reply_to_message: 'MockMessage' = None,
                 reply_markup: ReplyMarkup = None,
                 **_kwargs: Any):
        super().__init__(
            chat=chat,
            from_user=from_user,
            message_id=message_id,
            date=date,
            reply_to_message=reply_to_message,
            reply_markup=reply_markup,
            **_kwargs
        )
        self.bot = bot
        MockMessage.id_seq = MockMessage.id_seq + 1


def get_chat(chats: list[MockChat], chat_id: int = None, chat_index: int = None):
    if len(chats) == 0:
        raise Exception("No Chats")
    if len(chats) == 1:
        return chats[0]
    if len(chats) > 1 and (chat_id is None or chat_index is None):
        raise Exception("More than 1 chat, specify id")
    if chat_id is not None:
        return any(x for x in chats if x.id == chat_id)
    return chats[chat_index]

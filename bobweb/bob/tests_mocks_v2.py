import datetime
import itertools
import os
from typing import Any, Optional, Tuple
from unittest.mock import MagicMock, Mock

import django
import pytz
from telegram import Chat, User, Bot, Update, Message, CallbackQuery, ReplyMarkup
from telegram.ext import CallbackContext

from bobweb.bob import message_handler, command_service
from bobweb.bob.tests_msg_btn_utils import buttons_from_reply_markup, get_callback_data_from_buttons_by_text, \
    button_labels_from_reply_markup
from bobweb.bob.utils_common import split_to_chunks
from bobweb.bob.utils_format import fit_text, \
    form_single_item_with_padding, Align

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


class MockBot(Mock):  # This is inherited from bot as this Bot class is complicated
    new_id = itertools.count(start=1)

    def __init__(self, **kw):
        super().__init__(spec=Bot)
        self.id = next(MockBot.new_id)
        self.username = f'{chr(64 + self.id)}_bot'
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
        message = MockMessage(chat=chat, from_user=self.tg_user, bot=self, text=text, **_kwargs)

        # Add message to both users and chats messages
        self.messages.append(message)
        chat.messages.append(message)
        print_msg(message)
        return message

    # Edits own message with given id. If no id is given, edits last sent message.
    def edit_message_text(self, text: str, message_id: int = None, reply_markup=None, **kwargs: Any) -> 'MockMessage':
        if message_id is None:
            message_id = self.messages[-1].message_id
        message = [x for x in self.messages if x.message_id == message_id].pop()
        message.text = text
        message.reply_markup = reply_markup
        print_msg(message, is_edit=True)
        return message

    # Called when bot sends document
    def send_document(self, chat_id: int, document: bytes):
        chat = get_chat(self.chats, chat_id)
        chat.documents.append(document)


# # Multiple bots per not supported at least for now
# bot = MockBot()


class MockChat(Chat):
    new_id = itertools.count(start=1)

    def __init__(self,
                 id: int = None,
                 type: str = 'group'):
        super().__init__(
            id=id if id is not None else next(MockChat.new_id),
            type=type
        )
        self.title = 'mock_chat'

        self.messages: list[MockMessage] = []
        self.documents: list[bytes] = []
        self.users: list[MockUser] = []
        # bot.chats.append(self)
        self.bot: MockBot = MockBot()
        self.bot.chats.append(self)

    def last_bot_msg(self) -> 'MockMessage':
        if len(self.bot.messages) == 0:
            raise Exception('no bot messages in chat')
        return self.bot.messages[-1]

    def last_bot_txt(self) -> str:
        return self.last_bot_msg().text

    def last_user_msg(self) -> 'MockMessage':
        users_messages = [msg for msg in self.messages if not msg.from_user.is_bot]
        if len(users_messages) == 0:
            raise Exception('no user messages in chat')
        return users_messages[-1]

    def last_user_txt(self) -> str:
        return self.last_user_msg().text


class MockUser(User):
    new_id = itertools.count(start=1)

    def __init__(self,
                 id: int = None,
                 first_name: str = None,
                 is_bot: bool = False,
                 chat: MockChat = None,
                 **_kwargs: Any):
        id = id if id is not None else next(MockUser.new_id)
        first_name = first_name if first_name is not None else chr(64 + id)  # 65 = 'A', 66 = 'B' ...
        super().__init__(id, first_name, is_bot, username=first_name, **_kwargs)
        self.chats: list[MockChat] = []
        self.messages: list[MockMessage] = []
        if chat is not None:
            self.chats.append(chat)

    # Method for mocking an update that is received by bot's message handler
    # Chat needs to be given on the first update. On later one's if no chat is given, last chat is used as target
    def send_update(self,
                    text: str,
                    chat: MockChat = None,
                    context: CallbackContext = None,
                    reply_to_message: 'MockMessage' = None) -> 'MockMessage':
        if chat is None:
            chat = self.chats[-1]  # Last chat
        message = MockMessage(chat=chat, bot=chat.bot, from_user=self, text=text, reply_to_message=reply_to_message)

        # Add message to both users and chats messages
        self.messages.append(message)
        chat.messages.append(message)
        # Add chat to users chats, so that it is not required to be given later
        if chat not in self.chats:
            self.chats.append(chat)
        if self not in chat.users:
            chat.users.append(self)

        update = MockUpdate(message=message, effective_user=self)
        print_msg(message)
        message_handler.handle_update(update, context)
        return message

    def reply_to_bot(self, text: str):
        reply_to = self.messages[-1].chat.bot.messages[-1]  # Last bot message from chat that was last messaged
        self.send_update(text, reply_to_message=reply_to)

    # Simulates pressing a button from bot's message and sending update with inlineQuery to bot
    def press_button(self, label: str, msg_with_btns=None, context: CallbackContext = None):
        if msg_with_btns is None:  # Message not given, get last chats last message from bot
            msg_with_btns = self.chats[-1].bot.messages[-1]
        buttons = buttons_from_reply_markup(msg_with_btns.reply_markup)

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.data = get_callback_data_from_buttons_by_text(buttons, label)
        if callback_query.data is None:
            raise Exception('callback_data should not be None. Check that the buttons are as expected')

        update = MockUpdate(callback_query=callback_query, message=msg_with_btns)
        command_service.instance.reply_and_callback_query_handler(update, context)


# Update = Incoming update from telegram api. Every message and media post is contained in update
class MockUpdate(Update):
    new_id = itertools.count(start=1)

    def __init__(self,
                 message: 'MockMessage' = None,
                 edited_message: 'MockMessage' = None,
                 effective_user: 'MockUser' = None,
                 update_id: int = None,
                 **_kwargs: Any):
        effective_message = edited_message if edited_message is not None else message
        super().__init__(
            update_id=update_id if update_id is not None else next(MockUpdate.new_id),
            message=message,
            edited_message=edited_message,
            effective_message=effective_message,
            _effective_user=effective_user,
            **_kwargs
        )


# Single message. If received from Telegram API, is inside an update
class MockMessage(Message):
    new_id = itertools.count(start=1)

    def __init__(self,
                 chat: MockChat,
                 from_user: MockUser,
                 bot: MockBot = None,
                 message_id: int = None,
                 dt: datetime = None,
                 reply_to_message: 'MockMessage' = None,
                 reply_markup: ReplyMarkup = None,
                 **_kwargs: Any):
        if message_id is None:
            message_id = next(MockMessage.new_id)
        if dt is None:
            dt = datetime.datetime.now(tz=pytz.UTC)
        super().__init__(
            chat=chat,
            from_user=from_user,
            message_id=message_id,
            date=dt,
            reply_to_message=reply_to_message,
            reply_markup=reply_markup,
            **_kwargs
        )
        self.chat: MockChat = chat
        self.bot: MockBot = bot

    # Override real implementation of _quote function with mock implementation
    def _quote(self, quote: Optional[bool], reply_to_message_id: Optional[int]) -> Optional[int]:
        if reply_to_message_id is not None:
            return reply_to_message_id
        return None

    # Simulates user editing their message.
    # Not part of TPB API and should not be confused with Message.edit_text() method
    def edit_message(self, text: str, context: CallbackContext = None, **_kwargs: Any):
        self.text = text
        update = MockUpdate(edited_message=self, effective_user=self.from_user)
        message_handler.handle_update(update, context=context)


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


def init_chat_user() -> Tuple[MockChat, MockUser]:
    chat = MockChat()
    user = MockUser()
    user.chats.append(chat)
    return chat, user


message_time_format = '%d.%m.%Y %H.%M.%S'
message_id_limit = 3
username_limit = 10
line_width_limit = 60
message_width_limit = 45
tab_width = 3

f = fit_text  # Make local short alias fot fit_text function


def print_msg(msg: MockMessage, reply_to: MockMessage = None, is_edit = False):
    align = Align.RIGHT if msg.from_user.is_bot else Align.LEFT
    padding_width = line_width_limit - message_width_limit
    padding_left = 0 if align == align.LEFT else padding_width
    pad = padding_left * ' '

    header = pad + msg_header(msg.message_id, msg.from_user, msg.date)
    reply_line = ''
    if reply_to is not None:
        reply_msg = reply_to.reply_to_message
        reply_line = pad + reply_to_line(reply_msg.message_id, reply_msg.from_user.username, reply_msg.text) + '\n'

    formatted_text = tabulated_msg_body(msg.text, align)
    buttons = buttons_row(msg, pad)
    console_msg = (pad + 'EDITED MESSAGE\n' if is_edit else '') + \
                  f'{header}\n' \
                  f'{reply_line}' \
                  f'{formatted_text}\n' \
                  f'{buttons}' \
                  f'{line_width_limit * "-"}'
    print(console_msg)


def msg_header(id: int, user: User | MockUser, dt: datetime):
    formatted_time = dt.strftime(message_time_format)
    type = 'bot' if user.is_bot else 'user'
    return f'{str(id)}. {type} {user.username[:10]} at {formatted_time}'


def reply_to_line(reply_to_id: int, username: str, msg: str):
    reply_msg_preview_limit = 16
    return f'{tab_width * " "}reply to: ({f(reply_to_id, message_width_limit)}|{f(username, username_limit)}|"{f(msg, reply_msg_preview_limit)}")'


def tabulated_msg_body(text, align: Align):
    padding_width = 0 if align == align.LEFT else line_width_limit - message_width_limit
    padding_left = padding_width * ' '
    line_change = '../'
    rows = text.split('\n')
    all_rows = []
    for i, r in enumerate(rows):
        if 'tulee ensin luoda uusi ky' in r:
            pass

        if len(r) <= line_width_limit:
            all_rows.append(r)
        else:

            chunks = split_to_chunks(r, message_width_limit - len(line_change))
            for j, chunk in enumerate(chunks):
                line_end = line_change if j < len(chunks) - 1 else ''
                all_rows.append(chunk + line_end)

    result = ''
    for i, r in enumerate(all_rows):
        first_c = '"' if i == 0 else ' '
        last_item = i == len(all_rows) - 1
        last_c = '"' if last_item else ' '
        result += padding_left + first_c + r + last_c + ('' if last_item else '\n')

    return result


def buttons_row(msg: MockMessage, padding: str):
    if msg is None or msg.reply_markup is None:
        return ''
    return padding + str(button_labels_from_reply_markup(msg.reply_markup)) + '\n'


def user_join_notification(username: str):
    content = f'user {f(username, username_limit)} joined chat'
    return form_single_item_with_padding(content, line_width_limit, Align.CENTER)


def add_line_changes_if_too_lgon(text: str, n: int, char: str):
    result = ""
    for i, c in enumerate(text):
        result += c
        if (i + 1) % n == 0:
            result += char
    return result


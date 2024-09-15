import datetime
import io
import itertools
import os
from io import BufferedReader
from typing import Any, Optional, Tuple, List, Union
from unittest.mock import MagicMock, Mock

import django
import pytz
from telegram import Chat, User as PtbUser, Bot, Update, Message as PtbMessage, CallbackQuery, \
    InputMediaDocument, Voice, ReplyParameters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram._utils.types import JSONDict
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, Application
from telethon.tl.custom import Message as TelethonMessage
from telethon.tl.types import PeerUser, User as TelethonUser, MessageReplyHeader, PhotoSize, TypeMessageMedia, \
    MessageMediaPhoto

from bobweb.bob import message_handler, command_service, message_handler_voice, tests_chat_event_logger
from bobweb.bob.telethon_service import TelethonClientWrapper
from bobweb.bob.tests_msg_btn_utils import buttons_from_reply_markup, get_callback_data_from_buttons_by_text

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()

"""
    These mock classes extend actual Telegram-Python-Bot classes. As from PTB 20.0
    all PTB internal classes are immutable. However, we can go around this by calling
    '_unfreeze' method for each object after it's super constructor call. After that,
    each object can be more usable in the tests.
"""


class MockBot(Bot):  # This is inherited from both Mock and Bot
    new_id = itertools.count(start=1)

    def __init__(self, **kw):
        # PTB Library properties
        super().__init__(token="token")
        super()._unfreeze()
        self.__id = next(MockBot.new_id)
        self.__username = f'{chr(64 + self.id)}_bot'
        self.tg_user = MockUser(is_bot=True, first_name=self.__username)

        # Attributes for easier testing
        self.chats: list[MockChat] = []
        self.messages: list[MockMessage] = []

    @property
    def id(self) -> int:  # pylint: disable=C0103
        """:obj:`int`: Unique identifier for this bot."""
        return self.__id

    @property
    def username(self) -> str:
        """:obj:`str`: Bot's username."""
        return self.__username  # type: ignore

    # Message from bot to the chat
    async def send_message(self,
                           text: str,
                           chat_id: int = None,
                           photo: bytes = None,
                           reply_to_message_id: int = None,
                           reply_parameters: ReplyParameters | None = None,
                           *args: Any, **kwargs: Any) -> 'MockMessage':
        chat = get_chat(self.chats, chat_id)
        reply_to_message_id = reply_to_message_id or (reply_parameters.message_id if reply_parameters else None)
        message = MockMessage(chat=chat, from_user=self.tg_user, bot=self, text=text, photo=photo,
                              reply_to_message_id=reply_to_message_id, **kwargs)

        # Add message to both users and chats messages
        self.messages.append(message)
        chat.messages.append(message)
        tests_chat_event_logger.print_msg(message)
        return message

    # Edits own message with given id. If no id is given, edits last sent message.
    async def edit_message_text(self, text: str, chat_id: int, message_id: int = None, parse_mode: ParseMode = None,
                                reply_markup=None, **kwargs: Any) -> 'MockMessage':
        if message_id is None:
            message_id = self.messages[-1].message_id
        message = [x for x in self.messages if x.message_id == message_id and x.chat.id == chat_id].pop()
        message.text = text
        message.reply_markup = reply_markup
        self.messages.append(message)
        tests_chat_event_logger.print_msg(message, is_edit=True)
        return message

    async def edit_message_media(self, *args, **kwargs):
        # TODO: Implement edit_message_media mock implementation
        pass

    # Edits media message caption
    async def edit_message_caption(self, chat_id: int, message_id: int, caption: Optional[str] = None,
                                   reply_markup=None, parse_mode: ParseMode = None, **kwargs: Any):
        message = await self.edit_message_text(caption, chat_id, message_id, reply_markup)
        message.caption = caption
        return message

    # Called when bot sends a document
    async def send_document(self, chat_id: int, document: bytes, filename: str = None, **kwargs):
        chat = get_chat(self.chats, chat_id)
        chat.media_and_documents.append(document)

    # Called when bot sends an image
    async def send_photo(self, chat_id: int, photo: bytes, caption: str = None, parse_mode: ParseMode = None, **kwargs):
        chat = get_chat(self.chats, chat_id)
        # Caption is added to the text attribute as well as to the caption attribute. This is to reduce the amount of
        # confusion when testing media messages. However, in the real Python Telegram Bot API media messages have the
        # text in attribute named 'caption' and not 'text'
        message = MockMessage(chat=chat, from_user=self.tg_user, bot=self, text=caption, caption=caption,
                              parse_mode=parse_mode, photo=photo)
        chat.media_and_documents.append(photo)

        # Add message to both users and chats messages
        self.messages.append(message)
        chat.messages.append(message)
        tests_chat_event_logger.print_msg(message)
        return message

    async def send_media_group(self, chat_id: int, media: List[InputMediaDocument], **kwargs):
        captions = []
        for photo in media:
            captions.append(photo.caption)
            await self.send_photo(chat_id, photo.media.input_file_content)
        await self.send_message('\n'.join(captions), chat_id)

    async def send_chat_action(self, *args, **kwargs):
        pass  # For now, do nothing while testing

    async def send_audio(self, chat_id: int, audio: bytes, title: str = None, **kwargs):
        chat = get_chat(self.chats, chat_id)
        chat.media_and_documents.append(audio)
        if title is not None:
            await self.send_message(title, chat_id, **kwargs)

    async def delete_message(self, chat_id: Union[str, int], message_id: int, *args, **kwargs) -> bool:
        """ Mock implementation for deleting messages. """
        chat = get_chat(self.chats, chat_id)
        message = next((msg for msg in chat.messages if msg.id == message_id), None)
        if message:
            chat.messages.remove(message)
            tests_chat_event_logger.print_msg_delete_log(message)

    async def pin_chat_message(self, chat_id: int, message_id: int, *args, **kwargs) -> bool:
        pass  # For now, do nothing while testing

    async def unpin_chat_message(self, chat_id: int, message_id: int, *args, **kwargs) -> bool:
        pass  # For now, do nothing while testing


class MockChat(Chat):
    new_id = itertools.count(start=1)

    def __init__(self,
                 id: int = None,
                 type: str = 'group',
                 bot: MockBot = None):
        id = id or next(MockChat.new_id)
        super().__init__(id=id, type=type)
        super()._unfreeze()  # This is required to enable extending the actual class

        self.messages: list[MockMessage] = []
        self.media_and_documents: list[bytes | BufferedReader] = []
        self.users: list[MockUser] = []
        # Creates automatically new bot for the chat if none is given as parameter.
        # However, bot can be given as parameter, for example when it should be able to interact between multiple chats
        self.bot: MockBot = bot or MockBot()
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

    async def send_message(self, text: str, chat_id: int = None, **_kwargs: Any) -> 'MockMessage':
        return await self.bot.send_message(text, chat_id, **_kwargs)

    def get_bot(self) -> MockBot:
        """ Override PTB Chat class implementation """
        return self.bot


class MockUser(PtbUser, TelethonUser):
    """
    MockUser class for testing. Extends both Python Telegram Bot library's User and Telethon library's User. In
    addition, represents a simple abstraction of a user while testing where methods staring with 'send_' are used
    to mock users actions in real use scenario.
    """
    new_id = itertools.count(start=1)

    def __init__(self,
                 id: int = None,
                 first_name: str = None,
                 last_name: str = None,
                 is_bot: bool = False,
                 chat: MockChat = None,
                 **_kwargs: Any):
        # PTB Library properties
        id = id or next(MockUser.new_id)
        first_name = first_name or chr(64 + id)  # 65 = 'A', 66 = 'B' etc.
        super().__init__(id=id, first_name=first_name, is_bot=is_bot)
        super()._unfreeze()  # This is required to enable extending the actual class
        self.last_name = last_name
        self.username = self.first_name
        self.chats: list[MockChat] = []
        self.messages: list[MockMessage] = []
        if chat is not None:
            self.chats.append(chat)

        # Telethon properties
        self.bot = is_bot

    # Method for mocking an update that is received by bot's message handler. Overrides implementation in ptb User class.
    # Chat needs to be given on the first update. On later one's if no chat is given, last chat is used as target
    async def send_message(self,
                           text: str,
                           chat: MockChat = None,
                           context: CallbackContext = None,
                           reply_to_message: 'MockMessage' = None,
                           **kwargs) -> 'MockMessage':
        if chat is None:
            chat = self.chats[-1]  # Last chat
        message = MockMessage(
            # All extra keyword arguments are added to the constructor call
            chat=chat, bot=chat.bot, from_user=self, text=text, reply_to_message=reply_to_message, **kwargs)

        # Add message to both users and chats messages
        self.messages.append(message)
        chat.messages.append(message)
        # Add chat to users chats, so that it is not required to be given later
        if chat not in self.chats:
            self.chats.append(chat)
        if self not in chat.users:
            chat.users.append(self)

        update = MockUpdate(message=message)
        tests_chat_event_logger.print_msg(message)

        if not context:
            mock_application = Mock(spec=Application)
            mock_application.bot = chat.bot
            context = CallbackContext(application=mock_application)
        await message_handler.handle_update(update, context)
        return message

    async def reply_to_bot(self, text: str):
        reply_to = self.messages[-1].chat.bot.messages[-1]  # Last bot message from chat that was last messaged
        await self.send_message(text, reply_to_message=reply_to)

    # Simulates pressing a button from bots message and sending update with inlineQuery to bot
    async def press_button_with_text(self, text: str, msg_with_btns=None, context: CallbackContext = None):
        if msg_with_btns is None:  # Message not given, get last added chats last message from bot
            msg_with_btns = self.chats[-1].bot.messages[-1]
        buttons = buttons_from_reply_markup(msg_with_btns.reply_markup)

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.data = get_callback_data_from_buttons_by_text(buttons, text)
        if callback_query.data is None:
            raise Exception(f'tried to press button with text "{text}", but callback_query.data is None')

        update = MockUpdate(callback_query=callback_query, message=msg_with_btns)
        await command_service.instance.reply_and_callback_query_handler(update, context)

    async def press_button(self, button: InlineKeyboardButton, msg_with_btns=None, context: CallbackContext = None):
        return await self.press_button_with_text(button.text, msg_with_btns, context)

    async def send_voice(self, voice: Voice, chat=None, **kwargs) -> 'MockMessage':
        if chat is None:
            chat = self.chats[-1]  # Last chat
        # chat.media_and_documents.append(voice_file)
        message = MockMessage(chat=chat, bot=chat.bot, from_user=self, text=None, voice=voice)
        update = MockUpdate(message=message)

        await message_handler_voice.handle_voice_or_video_note_message(update)
        return message


# Update = Incoming update from telegram api. Every message and media post is contained in update
class MockUpdate(Update):
    new_id = itertools.count(start=1)

    def __init__(self,
                 message: 'MockMessage' = None,
                 edited_message: 'MockMessage' = None,
                 update_id: int = None,
                 callback_query: CallbackQuery = None):
        update_id = update_id or next(MockUpdate.new_id)
        super().__init__(update_id=update_id)
        super()._unfreeze()  # This is required to enable extending the actual class

        self.message = message
        self.edited_message = edited_message
        self.callback_query = callback_query
        self._bot = self.effective_message._bot if self.edited_message else None

    # Overriding implementation that just calls str() on the object
    def to_dict(self, recursive: bool = True) -> JSONDict:
        return f'{{"update_id": {self.update_id}}}'


# Single message. If received from Telegram API, is inside an update
# Represents both PTB and Telethon mock message
class MockMessage(PtbMessage, TelethonMessage):
    new_id = itertools.count(start=1)

    def __init__(self,
                 chat: MockChat,
                 from_user: MockUser,
                 bot: MockBot = None,
                 message_id: int = None,
                 dt: datetime = None,
                 reply_to_message: 'MockMessage' = None,
                 reply_to_message_id: int = None,
                 reply_markup: InlineKeyboardMarkup = None,
                 parse_mode: ParseMode = None,
                 text: str = None,
                 caption: str = None,
                 photo: Tuple[PhotoSize] = None,
                 voice: Voice = None,
                 media: Optional['TypeMessageMedia'] = None,
                 # args and kwargs added to prevent unexpected argument exception
                 *args, **kwargs):
        if message_id is None:
            message_id = next(MockMessage.new_id)
        if dt is None:
            dt = datetime.datetime.now(tz=pytz.UTC)
        # PTB Message properties
        super().__init__(message_id=message_id, date=dt, chat=chat)
        super()._unfreeze()
        self.from_user = from_user
        self.text = text
        self.caption = caption
        self.reply_to_message: 'MockMessage' = reply_to_message or find_message(chat, reply_to_message_id)
        self.reply_markup = reply_markup
        self._bot: MockBot = bot or chat.bot
        self.photo = photo
        self.grouped_id = None
        self.video_note = None
        self.parse_mode = parse_mode
        self.voice = voice
        # Telethon Message properties
        self.message = text
        self.media = media
        if media is None and photo is not None:
            self.media = MessageMediaPhoto(photo=photo)
        self.from_id: PeerUser = PeerUser(from_user.id)

    @property  # Telethon Message property that cannot be set
    def reply_to(self) -> MessageReplyHeader | None:
        if self.reply_to_message:
            return MessageReplyHeader(reply_to_msg_id=self.reply_to_message.message_id)
        return None

    @property
    def reply_to_msg_id(self):
        return self.reply_to.reply_to_msg_id if self.reply_to_message else None

    # Simulates user editing their message.
    # Not part of TPB API and should not be confused with Message.edit_text() method
    # Message.edit_text() calls internally Bot.edit_message_text(), which is mocked in MockBot class
    async def edit_message(self, text: str, reply_markup: InlineKeyboardMarkup = None, context: CallbackContext = None):
        self.text = text
        update = MockUpdate(edited_message=self)
        await message_handler.handle_update(update, context=context)

    def __repr__(self):
        """ Overridden representation to be used when objects are presented by debugger"""
        return (f"message id:{self.id} | user: {self.from_user.username}: "
                f"\"{self.text[:30] + '...' if len(self.text) > 27 else self.text}\"")


class MockTelethonClientWrapper(TelethonClientWrapper):
    # Mock image url in base64 returned by 'download_all_messages_image_bytes'
    mock_image_url = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/4QAiRXhpZgAATU0AKgAAAAgAAQESAAMAAAABAAEAAAAAAAD/2wBDAAIBAQIBAQICAgICAgICAwUDAwMDAwYEBAMFBwYHBwcGBwcICQsJCAgKCAcHCg0KCgsMDAwMBwkODw0MDgsMDAz/2wBDAQICAgMDAwYDAwYMCAcIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAz/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD5rooor8DP9oD/2Q=='

    """ Mock class from TelethonClientWrapper. Uses MockBots chat and message collections to fetch from. """

    def __init__(self, bot: MockBot):
        super().__init__()
        self.bot: MockBot = bot

    async def find_message(self, chat_id: int, msg_id) -> MockMessage:
        chat: MockChat = await self.find_chat(chat_id)
        return find_message(chat, msg_id)

    async def find_user(self, user_id: int) -> MockUser | None:
        if self.bot.tg_user.id == user_id:
            return self.bot.tg_user

        for chat in self.bot.chats:
            for user in chat.users:
                if user.id == user_id:
                    return user
        return None

    async def find_chat(self, chat_id: int) -> MockChat | None:
        for chat in self.bot.chats:
            if chat.id == chat_id:
                return chat
        return None

    async def download_all_messages_image_bytes(self, messages: List[MockMessage]) -> List[io.BytesIO]:
        return [await mock_async_get_image()]


async def mock_async_get_image(*args, **kwargs) -> io.BytesIO:
    """ This mock implementation retuns bytes from 1x1 red pixel jpeg image """
    with open('bobweb/bob/resources/test/red_1x1_pixel.jpg', "rb") as file:
        return io.BytesIO(file.read())


def find_message(chat: MockChat, msg_id) -> Optional[MockMessage]:
    if msg_id is None:
        return None
    for message in chat.messages:
        if message.message_id == msg_id:
            return message
    return None


def get_chat(chats: list[MockChat], chat_id: int = None) -> Optional[MockChat]:
    if len(chats) == 0:
        raise Exception("No Chats")
    if len(chats) == 1 and chat_id is None:
        return chats[0]
    if len(chats) > 1 and chat_id is None:
        raise Exception("More than 1 chat, specify id")
    if chat_id is not None:
        for chat in chats:
            if chat.id == chat_id:
                return chat
    return None


def init_chat_user() -> Tuple[MockChat, MockUser]:
    """ Creates new mock chat and mock user that is added as a member to the chat """
    user = MockUser()
    chat = MockChat()
    user.chats.append(chat)
    return chat, user


def init_private_chat_and_user() -> Tuple[MockChat, MockUser]:
    """ Creates a private chat between bot and a user. Differs from group chat in that this only has one user and
    the chat id is the same as the users id """
    chat, user = init_chat_user()
    chat.id = user.id  # Set users id as the chat id
    return chat, user

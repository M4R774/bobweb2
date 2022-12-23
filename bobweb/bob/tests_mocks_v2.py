import datetime
import os
from typing import Any
from unittest.mock import MagicMock, Mock

import django
import pytz
from telegram import Chat as TgChat, User as TgUser, Bot, Update
from bobweb.web.bobapp.models import Chat as ChatModel, DailyQuestionSeason, TelegramUser as TgUserModel, DailyQuestion, DailyQuestionAnswer

from bobweb.bob.utils_common import has

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


class ChatContext:
    def __init__(self):
        self.dq_id_seq = 0
        self.created_at = datetime.datetime.now(tz=pytz.UTC)
        self.chat: TgChat = create_chat()
        self.user = None

    def create_user(self):
        self.user = create_user(self.chat)
        return self.user


def create_chat():
    next_id = 1  # Extend later to include multiple chats
    # tg representation
    chat = Mock(spec=TgChat)
    chat.id = next_id

    # database representation
    ChatModel.objects.create(id=next_id, title=f'chat_{next_id}')

    # Extra
    chat.started_at = datetime.datetime.now(tz=pytz.UTC)
    chat.message_id_seq = 0

    return chat


def create_user(chat: TgChat):
    last_user = TgUserModel.objects.order_by('-id').first()
    next_id = last_user.id + 1 if has(last_user) else 1

    tg_user = Mock(spec=TgUser)
    tg_user.id = next_id
    tg_user.first_name = get_char(next_id)
    tg_user.username = tg_user.first_name
    tg_user.is_bot = False

    TgUserModel.objects.create(id=tg_user.id, username=tg_user.username)
    return TgUserModel.objects.get(id=tg_user.id)

def create_dq_season(tg_chat: TgChat):
    chat_entity = ChatModel.objects.get(id=tg_chat.id)
    created_at = datetime.datetime.now(tz=pytz.UTC)
    last_dq = DailyQuestionSeason.objects.order_by('-id').first()
    next_id = last_dq.id + 1 if has(last_dq) else 1
    DailyQuestionSeason.objects.create(id = next_id, chat=chat_entity, season_name=get_char(next_id),
                                                start_datetime=created_at)
    return DailyQuestionSeason.objects.get(id=next_id)


def get_char(i: int):
    return chr(64 + i), # 65 = 'A', 66 = 'B' ...






class MockChat(Mock):
    id_seq = 0

    def __init__(self,
                 id: int = id_seq + 1,
                 type: str = 'group'):
        super().__init__(spec=TgChat)
        MockChat.id_seq = MockChat.id_seq + 1
        self.id = id
        self.type = type

        self.msg_count = 0
        self.users: list[MockUser] = []


class MockUser(Mock):
    id_seq = 0

    def __init__(self,
                 id: int = id_seq +1,
                 first_name: str = chr(64 + id_seq), # 65 = 'A', 66 = 'B' ...
                 is_bot: bool = False,
                 **_kwargs: Any):
        super().__init__(spec=TgUser)
        MockUser.id_seq = MockUser.id_seq + 1
        self.id = id
        self.first_name = first_name
        self.is_bot = is_bot

        self.own_updates: list[MockUpdate] = []
        self.own_messages = []


class MockBot(MockUser):
    def __init__(self,
                 ):
        super().__init__(spec=Bot)
        self.tg_user.is_bot = True
        self.tg_user.username = self.tg_user.username + '_bot'


class MockUpdate(Mock):
    id_seq = 0

    def __init__(
            self,
            update_id: int = id_seq + 1,
            message: 'MockMessage' = None,
            edited_message: 'MockMessage' = None,
        ):
        super().__init__(spec=Update)
        MockUpdate.id_seq = MockUpdate.id_seq + 1
        self.update_id = id


class MockMessage(Mock):
    def __init__(self):
        pass



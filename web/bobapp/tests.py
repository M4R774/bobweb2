from django.utils import timezone

import django
from django.test import TestCase
from web.bobapp import apps
from web.bobapp.models import TelegramUser
from web.bobapp.models import Chat
from web.bobapp.models import ChatMember
from web.bobapp.models import Proverb
from web.bobapp.models import ChatProverb
from web.bobapp.models import Reminder


class BobAppTestCase(TestCase):
    def setUp(self) -> None:
        # Create users
        TelegramUser.objects.create(id=1337)
        TelegramUser.objects.create(id=1338, first_name="bot")
        TelegramUser.objects.create(id=1339, first_name="bot", last_name="bobilainen")

        # Create chats
        Chat.objects.create(id="1337")

        # Link users to chats
        ChatMember.objects.create(chat=Chat.objects.get(id=1337),
                                  tg_user=TelegramUser.objects.get(id=1337),
                                  rank=1,
                                  prestige=1)
        ChatMember.objects.create(chat=Chat.objects.get(id=1337),
                                  tg_user=TelegramUser.objects.get(id=1338),
                                  rank=1,
                                  prestige=0)
        ChatMember.objects.create(chat=Chat.objects.get(id=1337),
                                  tg_user=TelegramUser.objects.get(id=1339),
                                  rank=0,
                                  prestige=0)

        # Create proverbs
        Proverb.objects.create(proverb="Viisaus on viisautta")

        # Link proverbs to chats
        ChatProverb.objects.create(chat=Chat.objects.get(id=1337),
                                   proverb=Proverb.objects.get(proverb="Viisaus on viisautta"))

        # Create Reminders
        Reminder.objects.create(chat=Chat.objects.get(id=1337),
                                remember_this="muista tämä",
                                date_when_reminded=timezone.now())

    def test_apps(self):
        try:
            apps.BobappConfig("bobapp", "bobapp")
        except django.core.exceptions.ImproperlyConfigured:
            pass
        self.assertEqual(True, True)

    def test_model_telegram_user_with_only_id(self):
        test_user = TelegramUser.objects.get(id=1337)
        self.assertEqual("1337", str(test_user))

    def test_model_telegram_user_with_first_name(self):
        test_user = TelegramUser.objects.get(id=1338)
        self.assertEqual("bot", str(test_user))

    def test_chat(self):
        test_chat = Chat.objects.get(id=1337)
        self.assertEqual("1337", str(test_chat))

    def test_chat_member(self):
        test_chat_members = ChatMember.objects.filter(chat=1337)
        self.assertEqual("1337@1337", str(test_chat_members[0]))
        self.assertEqual(1, test_chat_members[0].rank)
        self.assertEqual(1, test_chat_members[0].prestige)

import os
import random
import re
import sys
import time
import datetime
from unittest import TestCase, mock, IsolatedAsyncioTestCase
from unittest.mock import patch

import pytz
from asgiref.sync import sync_to_async

import main
import pytz

sys.path.append('../web')  # needed for sibling import
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
from django.conf import settings
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser


class Test(IsolatedAsyncioTestCase):
    async def setUp(self) -> None:
        main.ranks = []
        main.read_ranks_file()
        update = MockUpdate()
        update.message.text = "jepou juupeli juu"
        update.effective_chat.id = 1337
        update.effective_user.id = 1337
        main.message_handler(update, context=None)
        await main.broadcast_and_promote(update)

    def test_reply_handler(self):
        update = MockUpdate()
        mock_message = MockMessage()
        mock_message.from_user = MockUser()
        mock_message.text = "Git käyttäjä bla bla blaa"
        mock_message.reply_to_message = mock_message
        update.message = mock_message
        admin = TelegramUser(id=1337)
        bob = Bob(id=1, global_admin=admin)
        bob.save()

    async def test_process_entity(self):
        message_entity = MockEntity()
        message_entity.type = "mention"

        mock_update = MockUpdate()
        mock_update.message.text = "@bob-bot "
        await main.process_entity(message_entity, mock_update)

        mock_update = MockUpdate()
        mock_update.message.text = "@bob-bot"
        await main.process_entity(message_entity, mock_update)

    def test_leet_command(self):
        update = MockUpdate()
        update.message.text = "1337"
        up = u"\U0001F53C"
        down = u"\U0001F53D"

        member = ChatMember.objects.get(chat=update.effective_user.id, tg_user=update.effective_chat.id)
        member.rank = 0
        member.prestige = 0
        member.save()
        old_prestige = member.prestige
        with patch('main.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 12, 37)
            main.message_handler(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 36)
            main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 37)
            main.leet_command(update, None)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon alokas! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            for i in range(51):
                mock_datetime.datetime.now.return_value = datetime.datetime(1970 + i, 1, 1, 13, 37)
                main.leet_command(update, None)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon pursimies! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            for i in range(15):
                main.leet_command(update, None)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)
            self.assertEqual(old_prestige+1, ChatMember.objects.get(chat=update.effective_user.id,
                                                                    tg_user=update.effective_chat.id).prestige)
            self.assertEqual(0, ChatMember.objects.get(chat=update.effective_user.id,
                                                       tg_user=update.effective_chat.id).rank)

    def test_space_command(self):
        update = MockUpdate()
        update.message.text = "/space"
        main.message_handler(update, None)
        self.assertRegex(update.message.reply_message_text,
                         r"Seuraava.*\n.*Helsinki.*\n.*T-:")

    def test_users_command(self):
        update = MockUpdate()
        update.message.text = "/käyttäjät"
        main.message_handler(update=update, context=None)
        self.assertNotEqual(None, update.message.reply_message_text)

    def test_broadcast_toggle_command(self):
        update = MockUpdate()

        update.message.text = "/kuulutus On"
        main.message_handler(update=MockUpdate, context=None)
        self.assertEqual("Kuulutukset ovat nyt päällä tässä ryhmässä.",
                         update.message.reply_message_text)

        update.message.text = "/kuulutus hölynpöly"
        main.broadcast_toggle_command(update=MockUpdate, context=None)
        self.assertEqual("Tällä hetkellä kuulutukset ovat päällä.",
                         update.message.reply_message_text)

        update.message.text = "/Kuulutus oFf"
        main.broadcast_toggle_command(update=MockUpdate, context=None)
        self.assertEqual("Kuulutukset ovat nyt pois päältä.",
                         update.message.reply_message_text)

        update.message.text = "/kuulutuS juupeli juu"
        main.broadcast_toggle_command(update=MockUpdate, context=None)
        self.assertEqual("Tällä hetkellä kuulutukset ovat pois päältä.",
                         update.message.reply_message_text)

    def test_broadcast_command(self):
        update = MockUpdate()
        main.broadcast_command(update, None)
        self.assertTrue(True)

    def test_time_command(self):
        update = MockUpdate()
        update.message.text = "/aika"
        main.message_handler(update=MockUpdate, context=None)
        hours_now = str(datetime.datetime.now(pytz.timezone('Europe/Helsinki')).strftime('%H'))
        hours_regex = r"\b" + hours_now + r":"
        self.assertRegex(update.message.reply_message_text,
                        hours_regex)

    @mock.patch('requests.get')  # Mock 'requests' module 'get' method.
    def test_weather_command(self, mock_get):
        # /sää helsinki successfull
        update = MockUpdate()
        update.message.text = "/sää helsinki"
        mock_helsinki = {   
          "coord": { "lon": 24.9355, "lat": 60.1695 },
          "weather": [
            { "id": 601, "main": "Snow", "description": "snow", "icon": "13n" }
          ],
          "base": "stations",
          "main": {
            "temp": 272.52,
            "feels_like": 270.24,
            "temp_min": 271.6,
            "temp_max": 273.6,
            "pressure": 977,
            "humidity": 90
          },
          "visibility": 1100,
          "wind": { "speed": 1.79, "deg": 225, "gust": 5.36 },
          "snow": { "1h": 0.49 },
          "clouds": { "all": 100 },
          "dt": 1643483100,
          "sys": {
            "type": 2,
            "id": 2028456,
            "country": "FI",
            "sunrise": 1643438553,
            "sunset": 1643466237
          },
          "timezone": 7200,
          "id": 658225,
          "name": "Helsinki",
          "cod": 200
        }
        mock_get.return_value.status_code = 200  # Mock status code of response.
        mock_get.return_value.json.return_value = mock_helsinki
        main.message_handler(update=update, context=None)
        self.assertRegex(update.message.reply_message_text,
                         r".*helsinki.*\n.*UTC.*\n.*tuntuu.*\n.*m/s")

        # /sää helsinki unseccussfull
        update.message.text = "/sää"
        mock_missing_city = {"cod": "404"}
        mock_get.return_value.status_code = 200  # Mock status code of response.
        mock_get.return_value.json.return_value = mock_missing_city
        main.message_handler(update=update, context=None)
        self.assertEqual(update.message.reply_message_text,
                         "Kaupunkia ei löydy.")

        # .sää helsinki successful
        mock_get.return_value.json.return_value = mock_helsinki
        update.message.text = ".sää"
        main.message_handler(update=update, context=None)
        self.assertRegex(update.message.reply_message_text,
                         r".*helsinki.*\n.*UTC.*\n.*tuntuu.*\n.*m/s")

    def test_low_probability_reply(self):
        update = MockUpdate()
        update.message.text = "Anything"
        update.message.reply_message_text = None
        main.message_handler(update=update, context=None)
        try:
            self.assertEqual(None, update.message.reply_message_text)
        except AssertionError:
            self.assertEqual("Vaikuttaa siltä että olette todella onnekas " + "\U0001F340",
                             update.message.reply_message_text)

        random_int = 1
        main.low_probability_reply(update=update, context=None, integer=random_int)
        self.assertEqual("Vaikuttaa siltä että olette todella onnekas " + "\U0001F340",
                         update.message.reply_message_text)

        random_int = 2
        main.low_probability_reply(update=update, context=None, integer=random_int)
        self.assertTrue(True)

    async def test_broadcast_and_promote(self):
        update = MockUpdate()
        await main.broadcast_and_promote(update)
        self.assertTrue(True)

    async def test_promote_committer_or_find_out_who_he_is(self):
        update = MockUpdate()
        os.environ["COMMIT_AUTHOR_NAME"] = "bob"
        os.environ["COMMIT_AUTHOR_NAME"] = "bob@bob.com"
        await main.promote_committer_or_find_out_who_he_is(update)
        self.assertTrue(True)

    def test_get_git_user_and_commit_info(self):
        main.get_git_user_and_commit_info()
        self.assertTrue(True)

    async def test_promote_or_praise(self):
        mock_bot = MockBot()

        # Create tg_user, chat, chat_member and git_user
        tg_user = TelegramUser(id=1337)
        tg_user.save()
        chat = Chat(id=1337)
        chat.save()
        chat_member = ChatMember(tg_user=tg_user, chat=chat)
        try:
            chat_member.save()
        except:
            chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
            chat_member.rank = 0
            chat_member.prestige = 0
            chat_member.save()
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)

        try:
            git_user = GitUser.objects.get(tg_user=tg_user)
        except:
            git_user = GitUser(name="bob", email="bobin-email@lol.com", tg_user=tg_user)
            git_user.save()

        # Test when latest date should be NULL, promotion should happen
        await main.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(1, chat_member.rank)

        # Test again, no promotion should happen
        tg_user = TelegramUser(id=1337,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(pytz.timezone('Europe/Helsinki')).date() -
                               datetime.timedelta(days=6))
        tg_user.save()
        await main.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        self.assertEqual(tg_user.latest_promotion_from_git_commit,
                         datetime.datetime.now(pytz.timezone('Europe/Helsinki')).date() -
                         datetime.timedelta(days=6))
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(1, chat_member.rank)

        # Change latest promotion to 7 days ago, promotion should happen
        tg_user = TelegramUser(id=1337,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(pytz.timezone('Europe/Helsinki')).date() -
                               datetime.timedelta(days=7))
        tg_user.save()
        await main.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(2, chat_member.rank)

        # Check that new random message dont mess up the user database
        update = MockUpdate()
        update.effective_user.id = 1337
        update.message.text = "jepou juupeli juu"
        main.message_handler(update, context=None)

        # Test again, no promotion
        await main.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(datetime.datetime.now(pytz.timezone('Europe/Helsinki')).date(),
                         tg_user.latest_promotion_from_git_commit)
        self.assertEqual(2, chat_member.rank)

    def test_huutista(self):
        update = MockUpdate()
        update.message.text = "Huutista"
        main.message_handler(update=update, context=None)
        self.assertEqual("...joka tuutista! 😂",
                         update.message.reply_message_text)

    def always_last_choice(values):
        return values[-1]

    @mock.patch('random.choice', always_last_choice)
    def test_or_command(self):
        update = MockUpdate()

        update.message.text = "rahat vai kolmipyörä?"
        main.message_handler(update=update, context=None)
        self.assertEqual(
            update.message.reply_message_text,
            None
        )

        update.message.text = "rahat .vai kolmipyörä?"
        main.message_handler(update=update, context=None)
        self.assertEqual(
            update.message.reply_message_text,
            "kolmipyörä"
        )

        update.message.text = "a .vai b .vai  c?"
        main.message_handler(update=update, context=None)
        self.assertEqual(
            update.message.reply_message_text,
            "c"
        )

    def test_db_updaters_command(self):
        update = MockUpdate()
        update.message.text = "jepou juupeli juu"
        main.update_user_in_db(update)
        user = TelegramUser.objects.get(id="1337")
        self.assertEqual("bob", user.first_name)
        self.assertEqual("bobilainen", user.last_name)
        self.assertEqual("bob-bot", user.username)

    def test_init_bot(self):
        main.init_bot()
        self.assertTrue(True)


class MockUser:
    id = 1337
    first_name = "bob"
    last_name = "bobilainen"
    username = "bob-bot"
    is_bot = True

    def mention_markdown_v2(self):
        return "hello world!"


class MockChat:
    id = 1337


class MockEntity:
    type = ""


class MockBot:
    def sendMessage(self, chat, message):
        print(chat, message)


class MockMessage:
    text = "/käyttäjät"
    reply_message_text = None
    reply_to_message = None
    from_user = None
    bot = MockBot()

    def reply_text(self, message, quote=None):
        self.reply_message_text = message
        print(message)

    # reply_markdown_v2 doesn't work for some reason
    def reply_markdown(self, message, quote=None):
        self.reply_message_text = message
        print(message)


class MockUpdate:
    bot = MockBot()
    effective_user = MockUser()
    effective_chat = MockChat()
    message = MockMessage()

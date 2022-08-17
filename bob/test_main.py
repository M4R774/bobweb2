import filecmp
import os
import random
import re
import sys
import time
import datetime
from typing import Union, Any
from unittest import TestCase, mock, IsolatedAsyncioTestCase
from unittest.mock import patch

from telegram import PhotoSize
from telegram.message import Message
from telegram.chat import Chat
from telegram.files.inputfile import InputFile

import pytz
from asgiref.sync import sync_to_async
from telegram.utils.helpers import parse_file_input

import main
import pytz

import db_backup
import git_promotions
import message_handler
import weather_command
import database

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
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python ../web/manage.py migrate")

    def setUp(self) -> None:
        update = MockUpdate()
        update.message.text = "jepou juupeli juu"
        update.effective_chat.id = 1337
        update.effective_user.id = 1337
        main.message_handler(update)
        main.broadcast_and_promote(update)

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

    def test_process_entity(self):
        message_entity = MockEntity()
        message_entity.type = "mention"

        mock_update = MockUpdate()
        mock_update.message.text = "@bob-bot "
        git_promotions.process_entity(message_entity, mock_update)

        mock_update = MockUpdate()
        mock_update.message.text = "@bob-bot"
        git_promotions.process_entity(message_entity, mock_update)

    def test_empty_incoming_message(self):
        update = MockUpdate()
        update.message = None
        main.message_handler(update=update)
        self.assertEqual(update.message, None)

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
        with patch('message_handler.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 12, 37)
            main.message_handler(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 36)
            message_handler.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 37)
            message_handler.leet_command(update)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon alokas! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            message_handler.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)

            for i in range(51):
                mock_datetime.datetime.now.return_value = datetime.datetime(1970 + i, 1, 1, 13, 37)
                message_handler.leet_command(update)
            self.assertEqual("Asento! bob-bot ansaitsi ylennyksen arvoon pursimies! 🔼 Lepo. ",
                             update.message.reply_message_text)

            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 13, 38)
            for i in range(15):
                message_handler.leet_command(update)
            self.assertEqual("Alokasvirhe! bob-bot alennettiin arvoon siviilipalvelusmies. 🔽",
                             update.message.reply_message_text)
            self.assertEqual(old_prestige+1, ChatMember.objects.get(chat=update.effective_user.id,
                                                                    tg_user=update.effective_chat.id).prestige)
            self.assertEqual(0, ChatMember.objects.get(chat=update.effective_user.id,
                                                       tg_user=update.effective_chat.id).rank)

    def test_ruoka_command(self):
        update = MockUpdate()
        update.message.text = "/ruoka"
        main.message_handler(update)
        self.assertRegex(update.message.reply_message_text,
                         r"https://www.")

    def test_space_command(self):
        update = MockUpdate()
        update.message.text = "/space"
        main.message_handler(update)
        self.assertRegex(update.message.reply_message_text,
                         r"Seuraava.*\n.*Helsinki.*\n.*T-:")

    def test_users_command(self):
        update = MockUpdate()
        update.message.text = "/käyttäjät"
        main.message_handler(update=update)
        self.assertNotEqual(None, update.message.reply_message_text)

    def test_broadcast_toggle_command(self):
        update = MockUpdate()

        update.message.text = "/kuulutus On"
        message_handler.message_handler(update=update)
        self.assertEqual("Kuulutukset ovat nyt päällä tässä ryhmässä.",
                         update.message.reply_message_text)

        update.message.text = "/kuulutus hölynpöly"
        message_handler.broadcast_toggle_command(update=update)
        self.assertEqual("Tällä hetkellä kuulutukset ovat päällä.",
                         update.message.reply_message_text)

        update.message.text = "/Kuulutus oFf"
        message_handler.broadcast_toggle_command(update=update)
        self.assertEqual("Kuulutukset ovat nyt pois päältä.",
                         update.message.reply_message_text)

        update.message.text = "/kuulutuS juupeli juu"
        message_handler.broadcast_toggle_command(update=update)
        self.assertEqual("Tällä hetkellä kuulutukset ovat pois päältä.",
                         update.message.reply_message_text)

    async def test_broadcast_command(self):
        update = MockUpdate()
        await message_handler.broadcast_command(update)
        self.assertTrue(True)

    def test_time_command(self):
        update = MockUpdate()
        update.message.text = "/aika"
        main.message_handler(update=update)
        hours_now = str(datetime.datetime.now(pytz.timezone('Europe/Helsinki')).strftime('%H'))
        hours_regex = r"\b" + hours_now + r":"
        self.assertRegex(update.message.reply_message_text,
                        hours_regex)

    @mock.patch('os.getenv')
    @mock.patch('requests.get')  # Mock 'requests' module 'get' method.
    def test_weather_command(self, mock_get, mock_getenv):
        mock_getenv.return_value = "DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE"

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
        main.message_handler(update=update)
        self.assertRegex(update.message.reply_message_text,
                         r".*helsinki.*\n.*UTC.*\n.*tuntuu.*\n.*m/s")

        # /sää helsinki unseccussfull
        update.message.text = "/sää"
        mock_missing_city = {"cod": "404"}
        mock_get.return_value.status_code = 200  # Mock status code of response.
        mock_get.return_value.json.return_value = mock_missing_city
        main.message_handler(update=update)
        self.assertEqual(update.message.reply_message_text,
                         "Kaupunkia ei löydy.")

        # .sää helsinki successful
        mock_get.return_value.json.return_value = mock_helsinki
        update.message.text = ".sää"
        main.message_handler(update=update)
        self.assertRegex(update.message.reply_message_text,
                         r".*helsinki.*\n.*UTC.*\n.*tuntuu.*\n.*m/s")

    def test_help_command_all_prefixes(self):
        update = MockUpdate()

        for prefix in ['!', '.', '/']:
            update.message.text = prefix + "help"
            message_handler.message_handler(update=update)
            self.assertRegex(update.message.reply_message_text, r'Komento\s*| Selite')

    def test_help_command_requires_prefix(self):
        update = MockUpdate()
        update.message.text = "help"
        message_handler.message_handler(update=update)
        self.assertEqual(update.message.reply_message_text, None)

    def test_all_commands_except_help_have_help_text_defined(self):
        for (name, body) in message_handler.commands().items():
            if name != 'help':
                self.assertTrue(message_handler.HELP_TEXT in body)
                self.assertTrue(len(body[message_handler.HELP_TEXT]) >= 2)
                self.assertRegex(body[message_handler.HELP_TEXT][0], r'' + name)

    def test_all_commands_included_in_help_response(self):
        update = MockUpdate()
        update.message.text = "!help"
        message_handler.message_handler(update=update)
        reply = update.message.reply_message_text

        for (name, body) in message_handler.commands().items():
            if name != 'help' and message_handler.HELP_TEXT in body:
                # regex: linebreak followed by optional (.. ), optional command prefix, followed by command name
                self.assertRegex(reply, r'(\r\n|\r|\n)(.. )?' + message_handler.PREFIXES_MATCHER + '?' + name)

    def test_low_probability_reply(self):
        update = MockUpdate()
        update.message.text = "Anything"
        update.message.reply_message_text = None
        message_handler.message_handler(update=update)
        try:
            self.assertEqual(None, update.message.reply_message_text)
        except AssertionError:
            self.assertEqual("Vaikuttaa siltä että olette todella onnekas " + "\U0001F340",
                             update.message.reply_message_text)

        random_int = 1
        message_handler.low_probability_reply(update=update, integer=random_int)
        self.assertEqual("Vaikuttaa siltä että olette todella onnekas " + "\U0001F340",
                         update.message.reply_message_text)

        random_int = 2
        message_handler.low_probability_reply(update=update, integer=random_int)
        self.assertTrue(True)
        message_handler.low_probability_reply(update=update, integer=0)

    def test_broadcast_and_promote(self):
        update = MockUpdate()
        main.broadcast_and_promote(update)
        self.assertTrue(True)

    def test_promote_committer_or_find_out_who_he_is(self):
        update = MockUpdate()
        os.environ["COMMIT_AUTHOR_NAME"] = "bob"
        os.environ["COMMIT_AUTHOR_NAME"] = "bob@bob.com"
        git_promotions.promote_committer_or_find_out_who_he_is(update)
        self.assertTrue(True)

    def test_get_git_user_and_commit_info(self):
        git_promotions.get_git_user_and_commit_info()
        self.assertTrue(True)

    def test_promote_or_praise(self):
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
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(1, chat_member.rank)

        # Test again, no promotion should happen
        tg_user = TelegramUser(id=1337,
                               latest_promotion_from_git_commit=
                               datetime.datetime.now(pytz.timezone('Europe/Helsinki')).date() -
                               datetime.timedelta(days=6))
        tg_user.save()
        git_promotions.promote_or_praise(git_user, mock_bot)
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
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(2, chat_member.rank)

        # Check that new random message dont mess up the user database
        update = MockUpdate()
        update.effective_user.id = 1337
        update.message.text = "jepou juupeli juu"
        main.message_handler(update)

        # Test again, no promotion
        git_promotions.promote_or_praise(git_user, mock_bot)
        tg_user = TelegramUser.objects.get(id=1337)
        chat_member = ChatMember.objects.get(tg_user=tg_user, chat=chat)
        self.assertEqual(datetime.datetime.now(pytz.timezone('Europe/Helsinki')).date(),
                         tg_user.latest_promotion_from_git_commit)
        self.assertEqual(2, chat_member.rank)

    def test_huutista(self):
        update = MockUpdate()
        update.message.text = "Huutista"
        main.message_handler(update=update)
        self.assertEqual("...joka tuutista! 😂",
                         update.message.reply_message_text)

    def always_last_choice(values):
        return values[-1]

    @mock.patch('random.choice', always_last_choice)
    def test_or_command(self):
        update = MockUpdate()
        update.message.text = "rahat .vai kolmipyörä?"
        main.message_handler(update=update)
        self.assertEqual(
            update.message.reply_message_text,
            "kolmipyörä"
        )

        update.message.text = "a .vai b .vai  c?"
        main.message_handler(update=update)
        self.assertEqual(
            update.message.reply_message_text,
            "c"
        )

    def test_rules_of_acquisition(self):
        update = MockUpdate()
        update.message.text = ".sääntö 1"
        main.message_handler(update=update)
        self.assertEqual(
            update.message.reply_message_text,
            "Kun olet saanut heidän rahansa, älä koskaan anna niitä takaisin."
        )

        update.message.text = ".sääntö 299"
        main.message_handler(update=update)
        self.assertEqual(
            update.message.reply_message_text,
            "Kun käytät jotakuta hyväksesi, kannattaa muistaa kiittää. Seuraavalla kerralla on sitten "
            "helpompi hönäyttää. (Neelixin keksimä olematon sääntö)"
        )

        update.message.text = ".sääntö 300"
        main.message_handler(update=update)
        self.assertRegex(update.message.reply_message_text,
                         r'\d+\. ')

        update.message.text = ".sääntö yksi"
        main.message_handler(update=update)
        self.assertRegex(update.message.reply_message_text,
                         r'\d+\. ')

    def test_db_updaters_command(self):
        update = MockUpdate()
        update.message.text = "jepou juupeli juu"
        database.update_user_in_db(update)
        user = TelegramUser.objects.get(id="1337")
        self.assertEqual("bob", user.first_name)
        self.assertEqual("bobilainen", user.last_name)
        self.assertEqual("bob-bot", user.username)

    @mock.patch('os.getenv')
    @mock.patch('telegram.ext.Updater')
    def test_init_bot(self, mock_updater, mock_getenv):
        mock_updater.return_value = None
        mock_getenv.return_value = "DUMMY_ENV_VAR"
        with patch('main.Updater'):
            main.init_bot()

    async def test_backup_create(self):
        mock_bot = MockBot()
        global_admin = TelegramUser(id=1337)
        bob = Bob(id=1, global_admin=global_admin)
        bob.save()
        await db_backup.create(mock_bot)
        self.assertTrue(filecmp.cmp('../web/db.sqlite3', mock_bot.sent_document.name, shallow=False))


class MockUser:
    def __init__(self):
        self.id = 1337
        self.first_name = "bob"
        self.last_name = "bobilainen"
        self.username = "bob-bot"
        self.is_bot = True

    def mention_markdown_v2(self):
        return "hello world!"


class MockChat:
    def __init__(self):
        self.chat = Chat(1337, 'group')
        self.id = 1337


class MockEntity:
    def __init__(self):
        self.type = ""


class MockBot:
    def __init__(self):
        self.sent_document = None
        self.defaults = None

    def send_document(self, chat, file):
        self.sent_document = file
        print(chat, file)

    def sendMessage(self, chat, message):
        print(chat, message)

    def send_photo(self, chat_id, photo, caption):
        self.sent_photo = photo


class MockMessage:
    def __init__(self, chat: Chat):
        self.message: Message = Message(int(random.random()), datetime.datetime.now(), chat)
        self.text = "/käyttäjät"
        self.reply_message_text = None
        self.reply_to_message = None
        self.reply_image = None
        self.from_user = None
        self.message_id = None
        self.chat = MockChat()
        self.bot = MockBot()

    def reply_text(self, message, parse_mode=None, quote=None):
        self.reply_message_text = message
        print(message)

    # reply_markdown_v2 doesn't work for some reason
    def reply_markdown(self, message, quote=None):
        self.reply_message_text = message
        print(message)

    def reply_photo(self, image, caption, parse_mode=None, quote=None):
        photo: Union[str, 'InputFile', Any] = parse_file_input(image, PhotoSize, filename=caption)
        self.reply_image = photo
        self.reply_message_text = caption
        print(caption)


class MockUpdate:
    def __init__(self):
        self.bot = MockBot()
        self.effective_user = MockUser()
        self.effective_chat = MockChat()
        self.message = MockMessage(self.effective_chat.chat)

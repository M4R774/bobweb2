import os
import sys
import time

from django.test import TestCase

from bobweb.bob import main, database
from bobweb.bob.activities.activity_state import back_button
from bobweb.bob.command_settings import SettingsCommand

from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_msg_btn_utils import button_labels_from_reply_markup
from bobweb.bob.tests_utils import assert_command_triggers

import django

from bobweb.bob.utils_common import flatten

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
from bobweb.web.bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser


settings_command = '/asetukset'
time_txt = 'aika'


class SettingsCommandTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(SettingsCommandTests, cls).setUpClass()
        django.setup()
        os.system("python bobweb/web/manage.py migrate")

    def test_command_triggers(self):
        should_trigger = [settings_command, '!asetukset', '.asetukset', settings_command.capitalize()]
        should_not_trigger = ['asetukset', 'test /asetukset', '/asetukset test']
        assert_command_triggers(self, SettingsCommand, should_trigger, should_not_trigger)

    def test_pressing_button_toggles_property(self):
        chat, user = init_chat_user()
        user.send_message(settings_command)
        chat_entity = database.get_chat(chat.id)

        labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)
        self.assertTrue(chat_entity.time_enabled)
        self.assertIn('aika ✅', labels)

        user.press_button(time_txt)
        chat_entity = database.get_chat(chat.id)
        labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)

        # Now chat setting has been changed and button updated
        self.assertFalse(chat_entity.time_enabled)
        self.assertIn('aika ❌', labels)

        user.press_button(time_txt)
        chat_entity = database.get_chat(chat.id)
        labels = button_labels_from_reply_markup(chat.last_bot_msg().reply_markup)

        # Now chat setting has been changed and button updated
        self.assertTrue(chat_entity.time_enabled)
        self.assertIn('aika ✅', labels)

    def test_settings_are_chat_specific(self):
        chat1, user1 = init_chat_user()
        chat2, user2 = init_chat_user()

        user1.send_message(settings_command)
        user1.press_button(time_txt)
        chat_entity = database.get_chat(chat1.id)
        labels = button_labels_from_reply_markup(chat1.last_bot_msg().reply_markup)

        # Now chat setting has been changed and button updated
        self.assertFalse(chat_entity.time_enabled)
        self.assertIn('aika ❌', labels)

        chat2_entity = database.get_chat(chat2.id)
        self.assertTrue(chat2_entity.time_enabled)

        user2.send_message(settings_command)
        chat_entity = database.get_chat(chat2.id)
        labels = button_labels_from_reply_markup(chat2.last_bot_msg().reply_markup)

        # second chat should have setting on
        self.assertTrue(chat_entity.time_enabled)
        self.assertIn('aika ✅', labels)

    def test_toggle_off_command_does_not_work(self):
        chat, user = init_chat_user()

        # new message from bot can be inspected without delay when command is on
        user.send_message(f'/{time_txt}')
        self.assertIn('🕑', chat.last_bot_txt())

        user.send_message(settings_command)
        user.press_button('aika')  # toggle command off

        bot_msg_count = len(chat.bot.messages)
        user.send_message(f'/{time_txt}')

        time.sleep(0.1)  # No new message from bot even after delay
        self.assertEqual(bot_msg_count, len(chat.bot.messages))

    def test_should_notify_when_user_replies_to_settings_menu(self):
        chat, user = init_chat_user()
        user.send_message(settings_command)

        bot_msg = chat.last_bot_msg()
        user.send_message('could you please turn off the "HYVÄÄ HUOMENTA!"?', reply_to_message=bot_msg)
        self.assertIn('Muuta asetuksia täppäämällä niitä alapuolelta', chat.last_bot_txt())

    def test_when_back_button_is_pressed_bot_says_bye(self):
        chat, user = init_chat_user()
        user.send_message(settings_command)
        user.press_button(back_button.text)
        self.assertIn('Selvä, muutokset tallennettu. Takaisin nukkumaan 🤖💤', chat.last_bot_txt())


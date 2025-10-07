import asyncio
import time

import pytest
from django.test import TestCase

from bot import main, database
from bot.commands.settings import SettingsCommand, hide_menu_button, show_menu_button

from bot.tests_mocks_v2 import init_chat_user, assert_buttons_contain
from bot.tests_utils import assert_command_triggers

import django

TIME_ENABLED = 'aika ✅'
TIME_DISABLED = 'aika ❌'

settings_command = '/asetukset'
time_txt = 'aika'


@pytest.mark.asyncio
class SettingsCommandTests(django.test.TransactionTestCase):

    async def test_command_triggers(self):
        should_trigger = [settings_command, '!asetukset', '.asetukset', settings_command.capitalize()]
        should_not_trigger = ['asetukset', 'test /asetukset', '/asetukset test']
        await assert_command_triggers(self, SettingsCommand, should_trigger, should_not_trigger)

    async def test_pressing_button_toggles_property(self):
        chat, user = init_chat_user()
        await user.send_message(settings_command)
        chat_entity = database.get_chat(chat.id)

        self.assertTrue(chat_entity.time_enabled)
        assert_buttons_contain(self, chat.last_bot_msg(), TIME_ENABLED)

        await user.press_button_with_text(TIME_ENABLED)
        chat_entity = database.get_chat(chat.id)

        # Now chat setting has been changed and button updated
        self.assertFalse(chat_entity.time_enabled)
        assert_buttons_contain(self, chat.last_bot_msg(), TIME_DISABLED)

        await user.press_button_with_text(TIME_DISABLED)
        chat_entity = database.get_chat(chat.id)

        # Now chat setting has been changed and button updated
        self.assertTrue(chat_entity.time_enabled)
        assert_buttons_contain(self, chat.last_bot_msg(), TIME_ENABLED)

    async def test_settings_are_chat_specific(self):
        chat1, user1 = init_chat_user()
        chat2, user2 = init_chat_user()

        await user1.send_message(settings_command)
        await user1.press_button_with_text(TIME_ENABLED)
        chat_entity = database.get_chat(chat1.id)

        # Now chat setting has been changed and button updated
        self.assertFalse(chat_entity.time_enabled)
        assert_buttons_contain(self, chat1.last_bot_msg(), TIME_DISABLED)

        chat2_entity = database.get_chat(chat2.id)
        self.assertTrue(chat2_entity.time_enabled)

        await user2.send_message(settings_command)
        chat_entity = database.get_chat(chat2.id)

        # second chat should have setting on
        self.assertTrue(chat_entity.time_enabled)
        assert_buttons_contain(self, chat2.last_bot_msg(), TIME_ENABLED)

    async def test_toggle_off_command_does_not_work(self):
        chat, user = init_chat_user()

        # new message from bot can be inspected without delay when command is on
        await user.send_message(f'/{time_txt}')
        self.assertIn('🕑', chat.last_bot_txt())

        await user.send_message(settings_command)
        await user.press_button_with_text(TIME_ENABLED)  # toggle command off

        bot_msg_count = len(chat.bot.messages)
        await user.send_message(f'/{time_txt}')

        await asyncio.sleep(0.1)  # No new message from bot even after delay
        self.assertEqual(bot_msg_count, len(chat.bot.messages))

    async def test_should_notify_when_user_replies_to_settings_menu(self):
        chat, user = init_chat_user()
        await user.send_message(settings_command)

        bot_msg = chat.last_bot_msg()
        await user.send_message('could you please turn off the "HYVÄÄ HUOMENTA!"?', reply_to_message=bot_msg)
        self.assertIn('Tekstivastauksia ei tueta', chat.last_bot_txt())

    async def test_when_closing_settings_without_changes_then_no_changes_are_listed(self):
        chat, user = init_chat_user()
        # First as a group chat
        await user.send_message(settings_command)
        await user.press_button(hide_menu_button)
        self.assertIn('Ei muutoksia ryhmän asetuksiin', chat.last_bot_txt())
        # Then as a private chat
        chat.type = 'private'
        await user.send_message(settings_command)
        await user.press_button(hide_menu_button)
        self.assertIn('Ei muutoksia keskustelun asetuksiin', chat.last_bot_txt())

    async def test_when_closing_settings_then_changes_are_listed(self):
        chat, user = init_chat_user()
        await user.send_message(settings_command)
        await user.press_button_with_text(TIME_ENABLED)  # toggle command off
        await user.press_button(hide_menu_button)
        self.assertIn('- aika: ✅ -> ❌', chat.last_bot_txt())

    async def test_when_settings_closed_then_reopen_button_is_shown_and_it_opens_settings_menu(self):
        chat, user = init_chat_user()
        await user.send_message(settings_command)
        await user.press_button(hide_menu_button)

        assert_buttons_contain(self, chat.last_bot_msg(), show_menu_button)

        await user.press_button(show_menu_button)
        self.assertIn('Bobin asetukset tässä ryhmässä', chat.last_bot_txt())

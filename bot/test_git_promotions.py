from unittest import mock
from unittest.mock import AsyncMock

import pytest
import telegram
from asynctest import Mock
from django.test import TestCase
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bot import main, database, git_promotions
from bot.tests_mocks_v2 import MockBot

default_commit_message = 'Title\n\n* Description <quote>text</quote>'


async def mock_method_bad_request_error(*args, parse_mode, **kwargs):  #NOSONAR (S7503)
    if parse_mode == ParseMode.HTML:
        raise telegram.error.BadRequest("Can't parse entities")


@pytest.mark.asyncio
class TestGitPromotions(TestCase):

    @mock.patch('os.getenv', lambda key: default_commit_message)
    @mock.patch('bot.git_promotions.promote_committer_or_find_out_who_he_is', AsyncMock())
    @mock.patch('bot.broadcaster.broadcast')
    async def test_broadcast_and_promote_sends_message_with_expandable_quote(self, broadcast_mock: AsyncMock):
        bot = database.get_bot()
        bot.latest_startup_broadcast_message = None
        bot.save()
        context = Mock(spec=CallbackContext)
        context.bot = MockBot()

        await git_promotions.broadcast_and_promote(context)

        expected_message = '<blockquote expandable>Title\n\n* Description &lt;quote&gt;text&lt;/quote&gt;</blockquote>'
        broadcast_mock.assert_called_with(
            bot=context.bot,
            text=expected_message,
            parse_mode=ParseMode.HTML)

        bot = database.get_bot()
        self.assertEqual(default_commit_message, bot.latest_startup_broadcast_message)

    @mock.patch('os.getenv', lambda key: default_commit_message)
    @mock.patch('bot.git_promotions.promote_committer_or_find_out_who_he_is', AsyncMock())
    @mock.patch('bot.database.get_bot', Mock())
    @mock.patch('bot.broadcaster.broadcast')
    async def test_broadcast_and_promote_sends_without_expandable_quote_if_initial_sending_fails(self, broadcast_mock: AsyncMock):
        context = Mock(spec=CallbackContext)
        context.bot = MockBot()

        # Add throwing bad request as side effect to the mock
        broadcast_mock.side_effect = mock_method_bad_request_error

        with self.assertLogs(level='WARNING') as log:
            await git_promotions.broadcast_and_promote(context)
            self.assertIn('Tried to broadcast commit message with expandable quote', log.output[-1])

        # Called twice, second call has the original text and no parse mode
        # as the first call with them caused bad request
        self.assertEqual(2, broadcast_mock.call_count)
        broadcast_mock.assert_called_with(
            bot=context.bot,
            text=default_commit_message,
            parse_mode=None)

    @mock.patch('os.getenv', lambda key: default_commit_message)
    @mock.patch('bot.broadcaster.broadcast')
    async def test_broadcast_and_promote_sends_message_with_expandable_quote(self, broadcast_mock: AsyncMock):
        bot = database.get_bot()
        bot.latest_startup_broadcast_message = default_commit_message
        bot.save()
        context = Mock(spec=CallbackContext)
        context.bot = MockBot()

        await git_promotions.broadcast_and_promote(context)
        broadcast_mock.assert_called_with(bot=context.bot, text='Olin vain hiljaa hetken.')

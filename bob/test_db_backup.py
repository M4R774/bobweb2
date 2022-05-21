from unittest import IsolatedAsyncioTestCase
import filecmp

import unittest
import db_backup


class DBBackupTestCases(IsolatedAsyncioTestCase):
    async def test_backup_create(self):
        mock_bot = MockBot()
        await db_backup.create(mock_bot)
        self.assertTrue(filecmp.cmp('../web/db.sqlite3', mock_bot.sent_document.name, shallow=False))


if __name__ == '__main__':
    unittest.main()


class MockBot:
    def __init__(self):
        self.sent_document = None

    def send_document(self, chat, file):
        self.sent_document = file
        print(chat, file)

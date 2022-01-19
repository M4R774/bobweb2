from tabnanny import check
import unittest

from utilities import check_for_new_migrations


class Test(unittest.TestCase):
    def test_check_for_migrations_no_migrations(self):
        self.assertTrue(check_for_new_migrations.check_for_migrations())
    
    @unittest.skip("No models yet")
    def test_check_for_migrations_migrations_exist(self):
        self.assertFalse(check_for_new_migrations.check_for_migrations())
        
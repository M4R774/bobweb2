from tabnanny import check
import unittest

import check_for_new_migrations

NEW_MODEL_CLASS = '''
class NewReminder(models.Model):
    remember_this = models.TextField(unique=False)  # What to remind
    chat = models.ForeignKey("Chat", null=False, on_delete=models.CASCADE)  # Where to remind
    date_when_reminded = models.DateTimeField(null=False)  # When to remind

    class Meta:
        ordering = ["date_when_reminded"]

    def __str__(self):
        return str(self.remember_this)
'''


class Test(unittest.TestCase):
    def test_check_for_migrations_no_migrations(self):
        self.assertTrue(check_for_new_migrations.check_for_migrations())
    
    
    def test_check_for_migrations_migrations_exist(self):
        with open('../web/bobapp/models.py', 'a') as models_file:
            models_file.write(NEW_MODEL_CLASS)
        self.assertFalse(check_for_new_migrations.check_for_migrations())
        
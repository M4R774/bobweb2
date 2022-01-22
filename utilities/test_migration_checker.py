from ctypes import sizeof
from shutil import copyfile
import unittest
import os
import glob

import check_for_new_migrations


WEBAPP_DIR_PATH = "../web/bobapp/"
MODELS_PATH = f"{WEBAPP_DIR_PATH}models.py"
MIGRATION_PATH = "../web/bobapp/migrations/"

NEW_MODEL_CLASS = '''
class Ike(models.Model):
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
        self.assertFalse(check_for_new_migrations.uncreated_migrations_exist())
    
    def test_check_for_migrations_migrations_exist(self):
        copy_models_path = f"{WEBAPP_DIR_PATH}/copy_models"
        copyfile(MODELS_PATH,copy_models_path)
        
        with open(MODELS_PATH, "a") as models_file:
            models_file.write(NEW_MODEL_CLASS)
            models_file.close()
        self.assertTrue(check_for_new_migrations.uncreated_migrations_exist())
        
        os.remove(MODELS_PATH)
        file_list = glob.glob(f"{MIGRATION_PATH}/*_ike.py*")
        self.assertEquals(1, len(file_list))
        for file_path in file_list:
            print(f"removing file from path {file_path}")
            os.remove(file_path)
        copyfile(copy_models_path, MODELS_PATH)
        os.remove(copy_models_path)
        
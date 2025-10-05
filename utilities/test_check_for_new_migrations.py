import os
import unittest
from shutil import copyfile

from utilities import check_for_new_migrations

WEBAPP_DIR_PATH = "web/bobapp/"
MODELS_PATH = f"{WEBAPP_DIR_PATH}models.py"
MIGRATION_PATH = "web/bobapp/migrations/"

NEW_MODEL_CLASS = '''
class NewTestModel(models.Model):
    text_field = models.TextField()
'''


class TestNoUnmigratedChangesExist(unittest.TestCase):
    """
    This test is run as part of full test run (including CI/CD pipelines) to ensure that there are no new
    migrations that have not been created. If this test fails, run the following command in project root to
    create the migrations:
        python3.10 web/manage.py makemigrations --no-input
    """

    def test_check_no_new_migrations_exist(self):
        check_for_new_migrations.main()


class TestCheckMigrationsModule(unittest.TestCase):
    """ This tests the check_for_new_migrations module itself """
    def test_check_for_migrations_no_migrations(self):
        self.assertFalse(check_for_new_migrations.uncreated_migrations_exist())
    
    def test_check_for_migrations_migrations_exist(self):
        copy_models_path = f"{WEBAPP_DIR_PATH}/models_copy.py"
        copyfile(MODELS_PATH, copy_models_path)
        try:
            with open(MODELS_PATH, "a") as models_file:
                models_file.write(NEW_MODEL_CLASS)
                models_file.close()
            self.assertTrue(check_for_new_migrations.uncreated_migrations_exist())

        except Exception as e:
            self.fail(f"Test failed due to an unexpected exception: {e}")
        finally:
            # Clean up created test migration file and restore models.py
            os.remove(MODELS_PATH)
            copyfile(copy_models_path, MODELS_PATH)
            os.remove(copy_models_path)
        
from django.test import TestCase
import sys
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.web.settings")
django.setup()
sys.path.append("./web/web")

import settings
# settings.configure()
import urls
import wsgi

sys.path.append("./web")
import manage


class Test(TestCase):
    def setUp(self):
        pass

    def test_smoke(self):
        manage.main()
        self.assertTrue(True)


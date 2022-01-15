from django.test import TestCase
import sys
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.web.settings")
django.setup()
sys.path.append("C:/Users/Aleksi/harrasteprojektit/bobweb2/web/web")

import settings
# settings.configure()
import urls
import wsgi


class Test(TestCase):
    def setUp(self):
        pass

    def test_smoke(self):
        self.assertTrue(True)

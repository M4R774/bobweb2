import django
from django.test import TestCase
import bobapp.apps


class BobAppTestCase(TestCase):
    def test_apps(self):
        try:
            app_config = bobapp.apps.BobappConfig("bobapp", "bobapp")
        except django.core.exceptions.ImproperlyConfigured:
            pass

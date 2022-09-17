from django.test import TestCase
from web import settings
from web import urls
from web import wsgi
import manage


class DjangoTestCase(TestCase):
    def test_smoke(self):
        manage.main()
        self.assertTrue(True)

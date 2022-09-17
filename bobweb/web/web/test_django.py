from django.test import TestCase
from bobweb.web.web import settings
from bobweb.web.web import urls
from bobweb.web.web import wsgi
import manage


class DjangoTestCase(TestCase):
    def test_smoke(self):
        manage.main()
        self.assertTrue(True)

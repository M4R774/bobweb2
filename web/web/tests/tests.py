from django.test import TestCase

import sys
import os

from web import settings
from web import urls
from web import wsgi


class WebTestCase(TestCase):
    def setUp(self):
        pass

    def testSmoke(self):
        pass

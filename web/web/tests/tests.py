from django.test import TestCase

import sys
import os
sys.path.append(os.getcwd())
import settings
import urls
import wsgi


class WebTestCase(TestCase):
    def setUp(self):
        pass

    def testSmoke(self):
        pass

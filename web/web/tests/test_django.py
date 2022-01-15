from unittest import TestCase
#from django.test import TestCase
import sys
import os

from web import settings
from web import urls
from web import wsgi


class Test(TestCase):
    def setUp(self):
        pass

    def test_smoke(self):
        self.assertTrue(True)

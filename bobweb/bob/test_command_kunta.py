import os

from unittest import IsolatedAsyncioTestCase, mock

from PIL import Image

from bobweb.bob.command_kunta import KuntaCommand
from bobweb.bob.tests_utils import assert_command_triggers

import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


def create_mock_image(*args, **kwargs) -> Image:
    return Image.new(mode='RGB', size=(1, 1))


@mock.patch('bobweb.bob.command_kunta.generate_and_format_result_image', create_mock_image)
class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python bobweb/web/manage.py migrate")

    def test_command_triggers(self):
        should_trigger = ['/kunta', '!kunta', '.kunta', '/KUNTA', '/kunta test']
        should_not_trigger = ['kunta', 'test /kunta']
        assert_command_triggers(self, KuntaCommand, should_trigger, should_not_trigger)

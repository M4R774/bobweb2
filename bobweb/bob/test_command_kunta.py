import os

from unittest import IsolatedAsyncioTestCase, mock

import PIL
import django
import shapely
from PIL import Image
from django.core import management
from django.test import TestCase

from bobweb.bob import command_kunta
from bobweb.bob.command_kunta import KuntaCommand
from bobweb.bob.tests_utils import assert_command_triggers


def create_mock_image(*args, **kwargs) -> Image:
    return Image.new(mode='RGB', size=(1, 1))


@mock.patch('bobweb.bob.command_kunta.generate_and_format_result_image', create_mock_image)
class TestCommandKuntaWithMockedImageGenerator(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(TestCommandKuntaWithMockedImageGenerator, cls).setUpClass()
        management.call_command('migrate')

    async def test_command_triggers(self):
        should_trigger = ['/kunta', '!kunta', '.kunta', '/KUNTA', '/kunta test']
        should_not_trigger = ['kunta', 'test /kunta']
        await assert_command_triggers(self, KuntaCommand, should_trigger, should_not_trigger)


class TestCommandKuntaWithoutMocks(django.test.TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(TestCommandKuntaWithoutMocks, cls).setUpClass()
        management.call_command('migrate')

    async def test_firefox_and_selenium_works_when_to_png_is_called(self):
        """
        Test that does actual municipality map image rendering using real implementation. Added so that this can be
        tested in the running environment.
        """
        command = KuntaCommand()
        kunta = command.kuntarajat[0]
        kunta_geo = shapely.geometry.shape(kunta["geometry"])

        # Render image
        image: PIL.Image.Image = command_kunta.generate_and_format_result_image(kunta_geo, render_delay_seconds=0)

        # Just make sure that image has height, width and size
        self.assertTrue(image.height > 1)
        self.assertTrue(image.width > 1)

import os
import sys

from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import patch, MagicMock

from PIL import Image
from PIL.JpegImagePlugin import JpegImageFile


import main

from bob.dallemini_command import convert_base64_strings_to_images, get_3x3_image_compilation, get_save_location
from bob.test.resources.images_base64_dummy import base64_dummy_images
from test_main import MockUpdate

sys.path.append('../web')  # needed for sibling import
import django
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
from django.conf import settings
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python ../web/manage.py migrate")


    def test_prompt_command_no_prompt(self):
        update = MockUpdate()
        update.message.text = '/dallemini'
        main.message_handler(update)
        expected_reply = 'Anna jokin syöte komennon jälkeen. \'[.!/]prompt [syöte]\''
        self.assertEqual(expected_reply, update.message.reply_message_text)

    # # Mock not working as expected
    # @mock.patch('dallemini_command.generate_result_image')
    # def test_prompt_command_with_prompt(self, mock_generate_result_image):
    #     mock_generate_result_image.return_value = 'test/resources/test_get_3x3_image_compilation-expected.jpeg'
    #     update = MockUpdate()
    #     update.message.text = '/dallemini eating pizza on top of the empire state building with king kong'
    #     main.message_handler(update)
    #     expected_reply = '"_eating pizza on top of the empire state building with king kong_"'
    #     self.assertEqual(expected_reply, update.message.reply_message_text)

    def test_convert_base64_strings_to_images(self):
        images = convert_base64_strings_to_images(base64_dummy_images)
        self.assertEqual(len(images), 9)
        self.assertEqual(type(images[0]), JpegImageFile)

    def test_get_3x3_image_compilation(self):
        images = convert_base64_strings_to_images(base64_dummy_images)
        actual_image_obj = get_3x3_image_compilation(images)

        # Test dimensions to match
        expected_width = images[0].width * 3
        expected_height = images[0].height * 3
        self.assertEqual(expected_width, actual_image_obj.width, '3x3 image compilation width does not match')
        self.assertEqual(expected_height, actual_image_obj.height, '3x3 image compilation height does not match')

        # Save image to disk
        image_path = get_save_location() + 'test_get_3x3_image_compilation-actual.jpeg'
        actual_image_obj.save(image_path)

        # Load saved image from disk
        actual_image = Image.open(image_path)
        expected_image = Image.open('test/resources/test_get_3x3_image_compilation-expected.jpeg')

        # # To see the images tested uncomment this block
        # actual_image.show()
        # expected_image.show()
        # diff = ImageChops.difference(actual_image, expected_image)
        # diff.show()

        self.assertEqual(list(expected_image.getdata()), list(actual_image.getdata()))
        expected_image.close()
        actual_image.close()

        if os.path.exists(image_path):
            os.remove(image_path)



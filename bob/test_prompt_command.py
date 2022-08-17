import datetime
import io
import os
import sys

from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import patch, MagicMock

from PIL import Image, ImageChops
from PIL.JpegImagePlugin import JpegImageFile

import main

from dallemini_command import convert_base64_strings_to_images, get_3x3_image_compilation, create_or_get_save_location, \
    get_given_prompt, send_image_response, split_to_chunks, get_image_compilation_file_name
from test.resources.images_base64_dummy import base64_dummy_images
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

    def test_dallemini_command_no_prompt(self):
        update = MockUpdate()
        update.message.text = '/dallemini'
        main.message_handler(update)
        expected_reply = 'Anna jokin syöte komennon jälkeen. \'[.!/]prompt [syöte]\''
        self.assertEqual(expected_reply, update.message.reply_message_text)

    def test_get_given_prompt(self):
        message = '!dallemini test . test/test-test\ntest\ttest .vai test'
        prompt_expected = 'test . test/test-test\ntest\ttest .vai test'
        prompt_actual = get_given_prompt(message)
        self.assertEqual(prompt_expected, prompt_actual)

    # # Mock not working as expected
    # @mock.patch('dallemini_command.generate_result_image')
    # def test_prompt_command_with_prompt(self, mock_generate_result_image):
    #     mock_generate_result_image.return_value = 'test/resources/test_get_3x3_image_compilation-expected.jpeg'
    #     update = MockUpdate()
    #     update.message.text = '/dallemini eating pizza on top of the empire state building with king kong'
    #     main.message_handler(update)
    #     expected_reply = '"_eating pizza on top of the empire state building with king kong_"'
    #     self.assertEqual(expected_reply, update.message.reply_message_text)

    def test_send_image_response(self):
        update = MockUpdate()
        update.message.text = '.dallemini test'
        prompt = 'test'
        image_location = 'test/resources/test_get_3x3_image_compilation-expected.jpeg'
        send_image_response(update, prompt, image_location)

        # Message text should be in quotes and in italics
        self.assertEqual('"_test_"', update.message.reply_message_text)

        # Test reply image to be equal to one in the disk
        expected_image: Image = Image.open(image_location)

        actual_image_bytes = update.message.reply_image.field_tuple[1]
        actual_image_stream = io.BytesIO(actual_image_bytes)
        actual_image = Image.open(actual_image_stream)

        # If diff.getbbox() is None, images are same. https://stackoverflow.com/questions/35176639/compare-images-python-pil
        diff = ImageChops.difference(actual_image, expected_image)
        self.assertIsNone(diff.getbbox())

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
        image_path = create_or_get_save_location() + 'test_get_3x3_image_compilation-actual.jpeg'
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

    def test_split_to_chunks_basic_cases(self):
        iterable = [0, 1, 2, 3, 4, 5, 6, 7]
        chunk_size = 3
        expected = [[0, 1, 2], [3, 4, 5], [6, 7]]
        self.assertEquals(expected, split_to_chunks(iterable, chunk_size))

        iterable = []
        chunk_size = 3
        expected = []
        self.assertEquals(expected, split_to_chunks(iterable, chunk_size))

        iterable = ['a', 'b', 'c', 'd']
        chunk_size = 1
        expected = [['a'], ['b'], ['c'], ['d']]
        self.assertEquals(expected, split_to_chunks(iterable, chunk_size))

        iterable = None
        chunk_size = 1
        self.assertEquals([], split_to_chunks(iterable, chunk_size))

        iterable = ['a', 'b', 'c', 'd']
        chunk_size = -1
        self.assertEquals(['a', 'b', 'c', 'd'], split_to_chunks(iterable, chunk_size))

    def test_get_image_compilation_file_name(self):
        with patch('dallemini_command.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 1, 1)

            non_valid_name = '!"#¤%&/()=_:;/*-*+@£$€{{[[]}\@@$@£€£$[}  \t \n foobar.jpeg'
            expected = '1970-01-01_0101_dalle_mini_with_prompt_foobarjpeg.jpeg'
            self.assertEqual(expected, get_image_compilation_file_name(non_valid_name))



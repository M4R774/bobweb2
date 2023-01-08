import datetime
import io
import os
import sys

from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import patch

from PIL import Image
from PIL.JpegImagePlugin import JpegImageFile

from bobweb.bob import main
from bobweb.bob.tests_mocks_v1 import MockUpdate
from bobweb.bob.tests_utils import assert_has_reply_to, assert_no_reply_to, assert_reply_to_contain, \
    mock_response_with_code, assert_reply_equal, MockResponse, assert_get_parameters_returns_expected_value

from bobweb.bob.command_dallemini import convert_base64_strings_to_images, get_3x3_image_compilation, send_image_response, \
     get_image_file_name, DalleMiniCommand
from bobweb.bob.resources.test.images_base64_dummy import base64_mock_images

import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


def mock_response_200_with_base64_images(*args, **kwargs):
    return MockResponse(status_code=200,
                        content=str.encode(f'{{"images": {base64_mock_images},"version":"mega-bf16:v0"}}\n'))


# By default, if nothing else is defined, all request.post requests are returned with this mock
@mock.patch('requests.post', mock_response_200_with_base64_images)
class Test(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.system("python bobweb/web/manage.py migrate")

    def test_command_should_reply(self):
        assert_has_reply_to(self, '/dallemini')

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, 'dallemini')

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, 'test /dallemini')

    def test_text_after_command_should_reply(self):
        assert_has_reply_to(self, '/dallemini test')

    def test_no_prompt_gives_help_reply(self):
        assert_reply_equal(self, '/dallemini', "Anna jokin syöte komennon jälkeen. '[.!/]prompt [syöte]'")

    def test_reply_contains_given_prompt_in_italics_and_quotes(self):
        assert_reply_to_contain(self, '/dallemini 1337', ['"_1337_"'])

    def test_response_status_not_200_gives_error_msg(self):
        with mock.patch('requests.post', mock_response_with_code(403)):
            assert_reply_to_contain(self, '/dallemini 1337', ['Kuvan luominen epäonnistui. Lisätietoa Bobin lokeissa.'])

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!dallemini', DalleMiniCommand())

    def test_send_image_response(self):
        update = MockUpdate()
        update.effective_message.text = '.dallemini test'
        prompt = 'test'
        expected_image = Image.open('bobweb/bob/resources/test/test_get_3x3_image_compilation-expected.jpeg')
        send_image_response(update, prompt, expected_image)

        # Message text should be in quotes and in italics
        self.assertEqual('"_test_"', update.effective_message.reply_message_text)

        actual_image_bytes = update.effective_message.reply_image.field_tuple[1]
        actual_image_stream = io.BytesIO(actual_image_bytes)
        actual_image = Image.open(actual_image_stream)

        # make sure that the image looks like expected
        self.assert_images_are_similar_enough(expected_image, actual_image)

    def test_convert_base64_strings_to_images(self):
        images = convert_base64_strings_to_images(base64_mock_images)
        self.assertEqual(len(images), 9)
        self.assertEqual(type(images[0]), JpegImageFile)

    def test_get_3x3_image_compilation(self):
        images = convert_base64_strings_to_images(base64_mock_images)
        actual_image_obj = get_3x3_image_compilation(images)

        # Test dimensions to match
        expected_width = images[0].width * 3
        expected_height = images[0].height * 3
        self.assertEqual(expected_width, actual_image_obj.width, '3x3 image compilation width does not match')
        self.assertEqual(expected_height, actual_image_obj.height, '3x3 image compilation height does not match')

        # Load expected image from disk
        expected_image = Image.open('bobweb/bob/resources/test/test_get_3x3_image_compilation-expected.jpeg')

        # make sure that the image looks like expected
        self.assert_images_are_similar_enough(expected_image, actual_image_obj)
        expected_image.close()

    def test_get_image_compilation_file_name(self):
        with patch('bobweb.bob.command_dallemini.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 1, 1)

            non_valid_name = '!"#¤%&/()=?``^*@£$€{[]}`\\~`` test \t \n foo-_b.a.r.jpeg'
            expected = '1970-01-01_0101_dalle_mini_with_prompt_test-foo-_barjpeg.jpeg'
            self.assertEqual(expected, get_image_file_name(non_valid_name))

    # # Test that images are similar enough using imagehash package
    # import imagehash
    # def assert_images_are_similar_enough(self, image1, image2):
    #     hash1 = imagehash.average_hash(image1)
    #     hash2 = imagehash.average_hash(image2)
    #     hash_bit_difference = hash1 - hash2
    #     tolerance = 5  # maximum bits that could be different between the hashes.
    #     self.assertLess(hash_bit_difference, tolerance)

    # Simple test that images are similar. Reduces images to be 100 x 100 and then compares contents
    # Reason for similarity check is that image saved to disk is not identical to a new image generated. That's why
    # we need to conclude that the images are just close enough similar.
    # based on: https://rosettacode.org/wiki/Percentage_difference_between_images#Python
    def assert_images_are_similar_enough(self, img1, img2):
        img1 = img1.resize((256, 256))
        img2 = img2.resize((256, 256))
        assert img1.mode == img2.mode, "Different kinds of images."

        pairs = zip(img1.getdata(), img2.getdata())
        if len(img1.getbands()) == 1:
            # for gray-scale jpegs
            dif = sum(abs(p1 - p2) for p1, p2 in pairs)
        else:
            dif = sum(abs(c1 - c2) for p1, p2 in pairs for c1, c2 in zip(p1, p2))

        ncomponents = img1.size[0] * img1.size[1] * 3
        actual_percentage_difference = (dif / 255.0 * 100) / ncomponents
        tolerance_percentage = 1
        self.assertLess(actual_percentage_difference, tolerance_percentage)

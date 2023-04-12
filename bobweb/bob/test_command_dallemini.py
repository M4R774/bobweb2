import datetime
import io
import os

from unittest import mock, skip
from django.test import TestCase
from unittest.mock import patch

from PIL import Image
from PIL.JpegImagePlugin import JpegImageFile

from bobweb.bob import main
from bobweb.bob.command import ChatCommand
from bobweb.bob.image_generating_service import convert_base64_strings_to_images, get_3x3_image_compilation
from bobweb.bob.resources.test.openai_api_dalle_images_response_dummy import openai_dalle_create_request_response_mock
from bobweb.bob.tests_mocks_v1 import MockUpdate
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    mock_response_with_code, assert_reply_equal, MockResponse, assert_get_parameters_returns_expected_value, \
    assert_command_triggers

from bobweb.bob.command_image_generation import send_images_response, get_image_file_name, DalleMiniCommand, \
    DalleCommand
from bobweb.bob.resources.test.dallemini_images_base64_dummy import base64_mock_images


@skip("Test base class that should not be tested by itself")
class ImageGenerationBaseTestClass(TestCase):
    """
    Base test class for image generation commands
    """
    command_class: ChatCommand.__class__ = None
    command_str: str = None
    expected_image_result: Image = None

    @classmethod
    def setUpClass(cls) -> None:
        super(ImageGenerationBaseTestClass, cls).setUpClass()
        os.system("python bobweb/web/manage.py migrate")

    @classmethod
    def tearDownClass(cls) -> None:
        super(ImageGenerationBaseTestClass, cls).tearDownClass()
        cls.expected_image_result.close()

    def test_command_triggers(self):
        should_trigger = [f'/{self.command_str}', f'!{self.command_str}', f'.{self.command_str}',
                          f'/{self.command_str.upper()}', f'/{self.command_str} test']
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}']
        assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    def test_no_prompt_gives_help_reply(self):
        assert_reply_equal(self, f'/{self.command_str}', "Anna jokin syöte komennon jälkeen. '[.!/]prompt [syöte]'")

    def test_reply_contains_given_prompt_in_italics_and_quotes(self):
        assert_reply_to_contain(self, f'/{self.command_str} 1337', ['"1337"'])

    def test_response_status_not_200_gives_error_msg(self):
        with mock.patch('requests.post', mock_response_with_code(403)):
            assert_reply_to_contain(self, f'/{self.command_str} 1337',
                                    ['Kuvan luominen epäonnistui. Lisätietoa Bobin lokeissa.'])

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, f'!{self.command_str}', self.command_class())

    def test_send_image_response(self):
        update = MockUpdate()
        update.effective_message.text = f'.{self.command_str} test'
        prompt = 'test'
        send_images_response(update, prompt, [self.expected_image_result])

        # Message text should be in quotes and in italics
        self.assertEqual('"test"', update.effective_message.reply_message_text)

        actual_image_bytes = update.effective_message.reply_image.field_tuple[1]
        actual_image_stream = io.BytesIO(actual_image_bytes)
        actual_image = Image.open(actual_image_stream)

        # make sure that the image looks like expected
        self.assert_images_are_similar_enough(self.expected_image_result, actual_image)

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

        # make sure that the image looks like expected
        self.assert_images_are_similar_enough(self.expected_image_result, actual_image_obj)

    def test_get_image_compilation_file_name(self):
        with patch('bobweb.bob.command_image_generation.datetime') as mock_datetime:
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


def dallemini_mock_response_200_with_base64_images(*args, **kwargs):
    return MockResponse(status_code=200,
                        content=str.encode(f'{{"images": {base64_mock_images},"version":"mega-bf16:v0"}}\n'))


@mock.patch('requests.post', dallemini_mock_response_200_with_base64_images)
class DalleminiCommandTests(ImageGenerationBaseTestClass):
    command_class = DalleMiniCommand
    command_str = 'dallemini'
    expected_image_result = Image.open('bobweb/bob/resources/test/test_get_3x3_image_compilation-expected.jpeg')

    @classmethod
    def setUpClass(cls) -> None:
        super(DalleminiCommandTests, cls).setUpClass()
        DalleMiniCommand.run_async = False


def openai_mock_response_200_with_base64_image(*args, **kwargs):
    return MockResponse(status_code=200, content=str.encode(openai_dalle_create_request_response_mock))


# # By default, if nothing else is defined, all request.post requests are returned with this mock
# class DalleCommandTests(ImageGenerationBaseTestClass):
#     command_class = DalleCommand.__class__
#     command_str = 'dalle'
#     expected_image_result = Image.open('bobweb/bob/resources/openai_api_dalle_images_response_processed_image.jpg')
#
#     @classmethod
#     def setUpClass(cls) -> None:
#         super(DalleCommandTests, cls).setUpClass()
#         DalleCommand.run_async = False



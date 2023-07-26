import datetime
import io
import os

from unittest import mock
from django.test import TestCase
from unittest.mock import patch

from PIL import Image
from PIL.JpegImagePlugin import JpegImageFile
from openai import InvalidRequestError
from openai.openai_response import OpenAIResponse

from bobweb.bob import main, image_generating_service
from bobweb.bob.command import ChatCommand
from bobweb.bob.image_generating_service import convert_base64_strings_to_images, get_3x3_image_compilation, \
    ImageGeneratingModel
from bobweb.bob.resources.test.openai_api_dalle_images_response_dummy import openai_dalle_create_request_response_mock
from bobweb.bob.tests_mocks_v1 import MockUpdate
from bobweb.bob.tests_mocks_v2 import init_chat_user
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    mock_response_with_code, assert_reply_equal, MockResponse, assert_get_parameters_returns_expected_value, \
    assert_command_triggers

from bobweb.bob.command_image_generation import send_images_response, get_image_file_name, DalleMiniCommand, \
    ImageGenerationBaseCommand, DalleCommand, get_text_in_html_str_italics_between_quotes
from bobweb.bob.resources.test.dallemini_images_base64_dummy import base64_mock_images


class ImageGenerationBaseTestClass(TestCase):
    """
    Base test class for image generation commands
    """
    command_class: ChatCommand.__class__ = None
    command_str: str = None
    expected_image_result: Image = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        os.system("python bobweb/web/manage.py migrate")

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        if cls.expected_image_result:
            cls.expected_image_result.close()

    def test_command_triggers(self):
        should_trigger = [f'/{self.command_str}', f'!{self.command_str}', f'.{self.command_str}',
                          f'/{self.command_str.upper()}', f'/{self.command_str} test']
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}']
        assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    def test_no_prompt_gives_help_reply(self):
        assert_reply_equal(self, f'/{self.command_str}', "Anna jokin syöte komennon jälkeen. '[.!/]prompt [syöte]'")

    def test_reply_contains_given_prompt_in_italics_and_quotes(self):
        assert_reply_to_contain(self, f'/{self.command_str} 1337', ['"<i>1337</i>"'])

    def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, f'!{self.command_str}', self.command_class())

    def test_send_image_response(self):
        update = MockUpdate()
        update.effective_message.text = f'.{self.command_str} test'
        caption = get_text_in_html_str_italics_between_quotes('test')
        send_images_response(update, caption, [self.expected_image_result])

        # Message text should be in quotes and in italics
        self.assertEqual('"<i>test</i>"', update.effective_message.reply_message_text)

        actual_image_bytes = update.effective_message.reply_image.field_tuple[1]
        actual_image_stream = io.BytesIO(actual_image_bytes)
        actual_image = Image.open(actual_image_stream)

        # make sure that the image looks like expected
        self.assert_images_are_similar_enough(self.expected_image_result, actual_image)

    def test_convert_base64_strings_to_images(self):
        images = convert_base64_strings_to_images(base64_mock_images)
        self.assertEqual(len(images), 9)
        self.assertEqual(type(images[0]), JpegImageFile)

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


def openai_api_mock_response_one_image(*args, **kwargs):
    return OpenAIResponse(openai_dalle_create_request_response_mock['data'], None)


def raise_safety_system_triggered_error(*args, **kwargs):
    raise InvalidRequestError(message='Your request was rejected as a result of our safety system. Your prompt '
                                      'may contain text that is not allowed by our safety system.', param=None)


@mock.patch('requests.post', dallemini_mock_response_200_with_base64_images)
class DalleminiCommandTests(ImageGenerationBaseTestClass):
    command_class = DalleMiniCommand
    command_str = 'dallemini'
    expected_image_result: Image = Image.open('bobweb/bob/resources/test/test_get_3x3_image_compilation-expected.jpeg')

    def test_converted_3x3_image_compilation_is_similar_to_expected(self):
        images = convert_base64_strings_to_images(base64_mock_images)
        actual_image_obj = get_3x3_image_compilation(images)

        # Test dimensions to match
        expected_width = images[0].width * 3
        expected_height = images[0].height * 3
        self.assertEqual(expected_width, actual_image_obj.width, '3x3 image compilation width does not match')
        self.assertEqual(expected_height, actual_image_obj.height, '3x3 image compilation height does not match')

        # make sure that the image looks like expected
        self.assert_images_are_similar_enough(self.expected_image_result, actual_image_obj)

    def test_response_status_not_200_gives_error_msg(self):
        with mock.patch('requests.post', mock_response_with_code(403)):
            assert_reply_to_contain(self, f'/{self.command_str} 1337',
                                    ['Kuvan luominen epäonnistui. Lisätietoa Bobin lokeissa.'])


@mock.patch('openai.Image.create', openai_api_mock_response_one_image)
@mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
@mock.patch('os.getenv', lambda key: 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE')
class DalleCommandTests(ImageGenerationBaseTestClass):
    command_class = DalleCommand
    command_str = 'dalle'
    expected_image_result: Image = Image.open('bobweb/bob/resources/test/openai_api_dalle_images_response_processed_image.jpg')

    def test_multiple_context_managers_and_asserting_raised_exception(self):
        """ More example than tests. Demonstrates how context manager can contain multiple definitions and confirms
            that actual api is not called """
        with (
            mock.patch('openai.Image.create', raise_safety_system_triggered_error),
            self.assertRaises(InvalidRequestError) as e,
        ):
            image_generating_service.generate_images('test prompt', ImageGeneratingModel.DALLE2)

    def test_bot_gives_notification_if_safety_system_error_is_triggered(self):
        with mock.patch('openai.Image.create', raise_safety_system_triggered_error):
            chat, user = init_chat_user()
            user.send_message('/dalle inappropriate prompt that should raise error')
            self.assertEqual(DalleCommand.safety_system_error_msg, chat.last_bot_txt())

    def test_image_sent_by_bot_is_similar_to_expected(self):
        chat, user = init_chat_user()
        user.send_message('/dalle some prompt')

        image_bytes_sent_by_bot = chat.media_and_documents[-1]
        actual_image: Image = Image.open(io.BytesIO(image_bytes_sent_by_bot))

        # make sure that the image looks like expected
        self.assert_images_are_similar_enough(self.expected_image_result, actual_image)

    def test_user_has_no_permission_to_use_api_gives_notification(self):
        with mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: False):
            chat, user = init_chat_user()
            user.send_message('/dalle whatever')
            self.assertEqual('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä', chat.last_bot_txt())


# Remove Base test class so that it is not ran by itself by any test runner
del ImageGenerationBaseTestClass

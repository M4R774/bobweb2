import datetime
import io
import logging
from unittest import mock
from unittest.mock import patch, AsyncMock, Mock

import django
import pytest
from PIL import Image
from PIL.JpegImagePlugin import JpegImageFile
from PIL.PngImagePlugin import PngImageFile
from aiohttp import ClientResponse
from django.core import management
from django.test import TestCase

import bobweb.bob.config
from bobweb.bob import main, image_generating_service, async_http, openai_api_utils
from bobweb.bob.command_image_generation import send_images_response, get_image_file_name, DalleCommand, \
    remove_all_dalle_commands_related_text
from bobweb.bob.image_generating_service import convert_base64_string_to_image
from bobweb.bob.resources.test.openai_api_dalle_images_response_dummy import openai_dalle_create_request_response_mock
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUpdate, MockMessage
from bobweb.bob.tests_utils import assert_reply_to_contain, \
    assert_reply_equal, assert_get_parameters_returns_expected_value, \
    assert_command_triggers, mock_openai_http_response
from bobweb.bob.utils_common import html_escape_and_wrap_with_expandable_quote


# Simple test that images are similar. Reduces images to be 100 x 100 and then compares contents
# Reason for similarity check is that image saved to disk is not identical to a new image generated. That's why
# we need to conclude that the images are just close enough similar.
# based on: https://rosettacode.org/wiki/Percentage_difference_between_images#Python
def assert_images_are_similar_enough(test_case, img1, img2):
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
    test_case.assertLess(actual_percentage_difference, tolerance_percentage)


async def mock_method_to_call_side_effect(*args, json, **kwargs):
    async def mock_json():
        prompt = json['prompt']
        return openai_dalle_create_request_response_mock(prompt)

    mock_response = Mock(spec=ClientResponse)
    mock_response.status = 200
    mock_response.json = mock_json
    return mock_response

mock_dalle_command_image_generation = AsyncMock(side_effect=mock_method_to_call_side_effect)


@pytest.mark.asyncio
@mock.patch('bobweb.bob.async_http.post', mock_dalle_command_image_generation)
@mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: True)
class DalleCommandTests(django.test.TransactionTestCase):
    bobweb.bob.config.openai_api_key = 'DUMMY_VALUE_FOR_ENVIRONMENT_VARIABLE'
    command_class = DalleCommand
    command_str = 'dalle'
    expected_image_result: Image = Image.open(
        'bobweb/bob/resources/test/openai_api_dalle_images_response_processed_image.jpg')

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        management.call_command('migrate')

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        if cls.expected_image_result:
            cls.expected_image_result.close()
        async_http.client.close()

    async def test_command_triggers(self):
        should_trigger = [f'/{self.command_str}', f'!{self.command_str}', f'.{self.command_str}',
                          f'/{self.command_str.upper()}', f'/{self.command_str} test']
        should_not_trigger = [f'{self.command_str}', f'test /{self.command_str}']
        await assert_command_triggers(self, self.command_class, should_trigger, should_not_trigger)

    async def test_no_prompt_gives_help_reply(self):
        await assert_reply_equal(self, f'/{self.command_str}',
                                 "Anna jokin syöte komennon jälkeen. '[.!/]prompt [syöte]'")

    async def test_known_openai_api_commands_and_price_info_is_removed_from_replied_messages_when_reply(self):
        # When dall-e command is used as a reply to another message, the other message is used as a prompt to the
        # dall-e image generation. If the message that is replied contains any content from previous OpenAi command
        # response, that content is removed from the message.
        expected_cases = [
            ('something', 'something'),
            ('"<i>something</i>"', 'something'),
            ('Abc\n\nKonteksti: 1 viesti.', 'Abc'),
            ('Abc\n\n', 'Abc'),
            ('/gpt /1 Abc', 'Abc')
        ]

        chat, user = init_chat_user()
        for case in expected_cases:
            original_message, expected_prompt = case
            # Mock async_http.post so that the /gpt command is mocked
            with mock.patch('bobweb.bob.async_http.post'):
                message = await user.send_message(original_message)

            with mock.patch('bobweb.bob.async_http.post') as mock_generate_images:
                # Now when user replies to another message with only the command,
                # it should use the other message as the prompt
                await user.send_message('/dalle', reply_to_message=message)
                self.assertEqual(expected_prompt, mock_generate_images.mock_calls[0].kwargs['json']['prompt'])

    def test_all_dalle_related_text_is_removed(self):
        self.assertEqual('', remove_all_dalle_commands_related_text('/dalle'))
        self.assertEqual('test', remove_all_dalle_commands_related_text('/dalle test'))
        self.assertEqual('/abc test',
                         remove_all_dalle_commands_related_text('/dalle /abc test'))

    async def test_reply_contains_given_prompt_in_italics_and_quotes(self):
        await assert_reply_to_contain(self,
                                      f'/{self.command_str} 1337',
                                      ['<blockquote expandable>1337</blockquote>'])

    async def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, f'!{self.command_str}', self.command_class())

    async def test_send_image_response(self):
        chat, user = init_chat_user()
        message = MockMessage(chat, user)
        update = MockUpdate(message=message)
        caption = html_escape_and_wrap_with_expandable_quote('test')
        await send_images_response(update, caption, [self.expected_image_result])

        # Message text should be in quotes and in italics
        self.assertEqual('<blockquote expandable>test</blockquote>', chat.last_bot_txt())

        actual_image_bytes = chat.media_and_documents[-1]
        actual_image_stream = io.BytesIO(actual_image_bytes)
        actual_image = Image.open(actual_image_stream)

        # make sure that the image looks like expected
        assert_images_are_similar_enough(self, self.expected_image_result, actual_image)

    async def test_convert_base64_strings_to_images(self):
        base64_image_string = openai_dalle_create_request_response_mock('revised prompt')['data'][0]['b64_json']
        image = convert_base64_string_to_image(base64_image_string)
        self.assertEqual(type(image), PngImageFile)

    async def test_get_image_compilation_file_name(self):
        with patch('bobweb.bob.command_image_generation.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(1970, 1, 1, 1, 1)

            non_valid_name = '!"#¤%&/()=?``^*@£$€{[]}`\\~`` test \t \n foo-_b.a.r.jpeg'
            expected = '1970-01-01_0101_dalle_mini_with_prompt_test-foo-_barjpeg.jpeg'
            self.assertEqual(expected, get_image_file_name(non_valid_name))

    async def test_bot_gives_notification_if_safety_system_error_is_triggered(self):
        mock_response_body = {'error': {'code': 'content_policy_violation', 'message': ''}}
        mock_method = mock_openai_http_response(status=400, response_json_body=mock_response_body)
        with (mock.patch('bobweb.bob.async_http.post', mock_method),
              self.assertLogs(level=logging.INFO) as logs):
            chat, user = init_chat_user()
            await user.send_message('/dalle inappropriate prompt that should raise error')
            self.assertEqual(openai_api_utils.safety_system_error_response_msg, chat.last_bot_txt())
            self.assertIn('Generating dall-e image rejected due to content policy violation', logs.output[-1])

    async def test_image_sent_by_bot_is_similar_to_expected(self):
        chat, user = init_chat_user()
        await user.send_message('/dalle some prompt')

        image_bytes_sent_by_bot = chat.media_and_documents[-1]
        actual_image: Image = Image.open(io.BytesIO(image_bytes_sent_by_bot))

        # make sure that the image looks like expected
        assert_images_are_similar_enough(self, self.expected_image_result, actual_image)

    async def test_user_has_no_permission_to_use_api_gives_notification(self):
        with mock.patch('bobweb.bob.openai_api_utils.user_has_permission_to_use_openai_api', lambda *args: False):
            chat, user = init_chat_user()
            await user.send_message('/dalle whatever')
            self.assertEqual('Komennon käyttö on rajattu pienelle testiryhmälle käyttäjiä', chat.last_bot_txt())

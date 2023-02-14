from unittest import mock

from django.test import TestCase


from bobweb.bob.command_huoneilma import interpret_measurement
from bobweb.bob.tests_utils import assert_has_reply_to, assert_no_reply_to, assert_reply_equal


class Test(TestCase):
    def test_command_should_reply(self):
        assert_has_reply_to(self, "/huoneilma")

    def test_no_prefix_no_reply(self):
        assert_no_reply_to(self, "huoneilma on tosi hyvä")

    def test_text_before_command_no_reply(self):
        assert_no_reply_to(self, "tunkkainen /huoneilma")

    def test_failed_measurement_response(self):
        response = interpret_measurement(None, None)
        self.assertEqual(response, "Anturiin ei saatu yhteyttä. Anturia 11"
                                   " yritettiin lukea pinnistä 17.")

    def test_succesful_measurement_response(self):
        response = interpret_measurement(33, 21)
        self.assertEqual(response, "Ilmankosteus: 33 %.\n" +
                                   "Lämpötila: 21 C°.")

    def test_partially_succesful_measurement_response(self):
        response = interpret_measurement(None, 21)
        self.assertEqual(response, "Anturiin ei saatu yhteyttä. Anturia 11"
                                   " yritettiin lukea pinnistä 17.")

    @mock.patch('bobweb.bob.command_huoneilma.is_raspberrypi', lambda: True)
    def test_mock_reading(self):
        assert_reply_equal(self, "/huoneilma", "Jokin meni vikaan antureita lukiessa.")

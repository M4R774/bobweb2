from unittest import mock

import django
import pytest
from django.test import TestCase


from bobweb.bob.command_huoneilma import interpret_measurement, HuoneilmaCommand
from bobweb.bob.tests_utils import assert_reply_equal, assert_command_triggers


@pytest.mark.asyncio
class Test(django.test.TransactionTestCase):
    async def test_command_triggers(self):
        should_trigger = ['/huoneilma', '!huoneilma', '.huoneilma', '/HUONEILMA']
        should_not_trigger = ['huoneilma', '/huoneilma test', 'huoneilma on tosi hyvä', 'tunkkainen /huoneilma']
        await assert_command_triggers(self, HuoneilmaCommand, should_trigger, should_not_trigger)

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
    async def test_mock_reading(self):
        await assert_reply_equal(self, "/huoneilma", "Jokin meni vikaan antureita lukiessa.")

import datetime

import pytz
from django.test import TestCase

from bot.resources.bob_constants import fitz
from bot.utils_common import next_weekday, prev_weekday, weekday_count_between, fitz_from


class TimeUtilitiesTests(TestCase):

    def test_next_weekday(self):
        dt = datetime.datetime
        self.assertEqual(dt(2000, 1,  3), next_weekday(dt(2000, 1, 1)))  # sat
        self.assertEqual(dt(2000, 1,  3), next_weekday(dt(2000, 1, 2)))  # sun
        self.assertEqual(dt(2000, 1,  4), next_weekday(dt(2000, 1, 3)))
        self.assertEqual(dt(2000, 1,  5), next_weekday(dt(2000, 1, 4)))
        self.assertEqual(dt(2000, 1,  6), next_weekday(dt(2000, 1, 5)))
        self.assertEqual(dt(2000, 1,  7), next_weekday(dt(2000, 1, 6)))
        self.assertEqual(dt(2000, 1, 10), next_weekday(dt(2000, 1, 7)))  # fri

    def test_prev_weekday(self):
        dt = datetime.datetime
        self.assertEqual(dt(1999, 12, 31), prev_weekday(dt(2000, 1, 1)))  # sat
        self.assertEqual(dt(1999, 12, 31), prev_weekday(dt(2000, 1, 2)))  # sun
        self.assertEqual(dt(1999, 12, 31), prev_weekday(dt(2000, 1, 3)))
        self.assertEqual(dt(2000,  1,  3), prev_weekday(dt(2000, 1, 4)))
        self.assertEqual(dt(2000,  1,  4), prev_weekday(dt(2000, 1, 5)))
        self.assertEqual(dt(2000,  1,  5), prev_weekday(dt(2000, 1, 6)))
        self.assertEqual(dt(2000,  1,  6), prev_weekday(dt(2000, 1, 7)))  # fri

    def test_get_weekday_count_between_2_days(self):
        dt = datetime.datetime
        between = weekday_count_between

        # 2022-01-01 is saturday
        self.assertEqual(0, between(dt(2000, 1, 1), dt(2000, 1, 1)))  # sat -> sat
        self.assertEqual(0, between(dt(2000, 1, 1), dt(2000, 1, 2)))  # sat -> sun
        # sat -> mon -  NOTE: as end date is not included, 0 week days
        self.assertEqual(0, between(dt(2000, 1, 1), dt(2000, 1, 3)))
        # sat -> tue - NOTE: monday is the only weekday in range
        self.assertEqual(1, between(dt(2000, 1, 1), dt(2000, 1, 4)))
        self.assertEqual(2, between(dt(2000, 1, 1), dt(2000, 1, 5)))
        self.assertEqual(3, between(dt(2000, 1, 1), dt(2000, 1, 6)))
        self.assertEqual(4, between(dt(2000, 1, 1), dt(2000, 1, 7)))
        self.assertEqual(5, between(dt(2000, 1, 1), dt(2000, 1, 8)))
        self.assertEqual(5, between(dt(2000, 1, 1), dt(2000, 1, 9)))
        self.assertEqual(5, between(dt(2000, 1, 1), dt(2000, 1, 10)))
        self.assertEqual(6, between(dt(2000, 1, 1), dt(2000, 1, 11)))

        # end date is not inclueded
        self.assertEqual(0, between(dt(2000, 1, 3), dt(2000, 1, 3)))
        self.assertEqual(1, between(dt(2000, 1, 3), dt(2000, 1, 4)))

        # order of dates does not matter
        self.assertEqual(6, between(dt(2000, 1, 11), dt(2000, 1, 1)))

        # Note, year cannot have less than 260 week days or more than 262
        # 366 day year starting on saturday will end on saturday.
        # More info https://en.wikipedia.org/wiki/Common_year_starting_on_Saturday
        self.assertEqual(260, between(dt(2000, 1, 1), dt(2001, 1, 1)))  # 365 days. 53 saturdays and sundays
        self.assertEqual(261, between(dt(2001, 1, 1), dt(2002, 1, 1)))  # 365 days, 52 saturdays and sundays
        self.assertEqual(262, between(dt(2004, 1, 1), dt(2005, 1, 1)))  # 366 days, 52 saturdays and sundays


class TestFitzFrom(TestCase):

    def test_none_input(self):
        self.assertIsNone(fitz_from(None))

    def test_standard_time(self):
        # Finnish standard time is UTC+02:00
        # 21.11.2022, 15:30 UTC
        dt = pytz.UTC.localize(datetime.datetime(2022, 11, 21, 15, 30))
        # 21.11.2022, 17:30 Finnish TZ
        expected_result = fitz.localize(datetime.datetime(2022, 11, 21, 17, 30))
        self.assertEqual(fitz_from(dt), expected_result)

    def test_daylight_savings_time(self):
        # Finnish daylight savings time is UTC+03:00
        # 21.06.2022, 15:30 UTC
        dt = pytz.UTC.localize(datetime.datetime(2022, 6, 21, 15, 30))
        # 21.06.2022, 18:30 Finnish TZ
        expected_result = fitz.localize(datetime.datetime(2022, 6, 21, 18, 30))
        self.assertEqual(fitz_from(dt), expected_result)

    def test_daylight_savings_time_period_before_dst_was_used(self):
        # DST continuous usage in Finland started in 1981
        # Finnish daylight savings time is UTC+03:00
        # 21.06.2022, 15:30 UTC
        dt = pytz.UTC.localize(datetime.datetime(1970, 6, 21, 15, 30))
        # 21.06.2022, 17:30 Finnish TZ
        expected_result = fitz.localize(datetime.datetime(1970, 6, 21, 17, 30))
        self.assertEqual(fitz_from(dt), expected_result)

    def test_non_utc_tz(self):
        # 21.11.2022, 15:30 UTC
        utc_dt = pytz.UTC.localize(datetime.datetime(2022, 11, 21, 15, 30))
        # Convert to Eastern Standard Time
        est_tz = pytz.timezone('US/Eastern')
        # 21.11.2022, 10:30 EST
        est_dt = utc_dt.astimezone(est_tz)
        # 21.11.2022, 10:30 Finnish TZ
        expected_result = fitz.localize(datetime.datetime(2022, 11, 21, 17, 30))
        self.assertEqual(fitz_from(est_dt), expected_result)

    def test_naive_utc_time(self):
        # 21.11.2022, 15:30 UTC
        utc_dt = datetime.datetime(2022, 11, 21, 15, 30)
        # 21.11.2022, 17:30 Finnish TZ
        expected_result = fitz.localize(datetime.datetime(2022, 11, 21, 17, 30))
        self.assertEqual(fitz_from(utc_dt), expected_result)

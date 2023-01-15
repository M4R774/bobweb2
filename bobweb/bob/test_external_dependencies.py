import datetime
import time

from django.test import TestCase
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory, TickingDateTimeFactory


class TestFreezeGunLibrary(TestCase):
    # Test to demonstrate how to use frozen guns freeze_time. Type of object depends on how 'freeze_gun' is called.
    # can be used as method decorator, with context manager or even as class decorator. For more info check
    # github: https://github.com/spulec/freezegun
    # pypi:   https://pypi.org/project/freezegun

    @freeze_time('2000-01-01', as_kwarg='clock')
    def test_method_decorator_works_on_unittest(self, clock: FrozenDateTimeFactory):
        # Any datetime call should return predefined datetime
        first_dt = datetime.datetime.now()
        self.assertEqual(datetime.datetime(2000, 1, 1), first_dt)

        time.sleep(0.00001)  # Delay to make sure there is a tick between these calls

        # Both datetimes should be equal
        second_dt = datetime.datetime.now()
        self.assertEqual(first_dt, second_dt)

        # Time can be moved relatively with +/- timedelta
        clock.tick(datetime.timedelta(days=366))
        self.assertEqual(datetime.date(2001, 1, 1), datetime.date.today())

        # New freeze_time can be set with a 'move_to' call. Both ISO and Finnish datetime formats are supported
        clock.move_to('2002-02-02')
        self.assertEqual(datetime.date(2002, 2, 2), datetime.date.today())

        clock.move_to('03.03.2003')
        self.assertEqual(datetime.date(2003, 3, 3), datetime.date.today())

    # Giving parameter tick=True creates a TickingDateTimeFactory which sets the start time but advances clock as usual
    # On every tick.
    @freeze_time(datetime.datetime(2000, 1, 2, 3, 4, 5, 6), tick=True, as_kwarg='clock')
    def test_with_TickingDateTimeFactory(self, clock: TickingDateTimeFactory):
        # First call should be at set date
        first_dt = datetime.datetime.now()
        self.assertEqual(datetime.date(2000, 1, 2), first_dt.date())

        time.sleep(0.00001)  # Delay to make sure there is a tick between these calls

        # Second datetime should not be same as the time has progressed as excpected
        second_dt = datetime.datetime.now()
        self.assertNotEqual(first_dt, second_dt)

    # Should work with context manager as well
    def test_with_context_manager(self):
        with freeze_time('2000-01-01') as clock:  # Use freeze_time to have full control of the clock
            clock: FrozenDateTimeFactory = clock  # Just to demonstrate type of object returned from context manager
            # Any datetime call should return predefined datetime
            self.assertEqual(datetime.datetime(2000, 1, 1), datetime.datetime.now())
            clock.tick(datetime.timedelta(days=366))
            self.assertEqual(datetime.date(2001, 1, 1), datetime.date.today())

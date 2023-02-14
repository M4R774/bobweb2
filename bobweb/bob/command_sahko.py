import datetime
import logging
from typing import List

import requests

from requests import Response

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand, regex_simple_command

from bobweb.bob.utils_common import fi_short_day_name_from_day_index

logger = logging.getLogger(__name__)

#  Based on https://github.com/slehtonen/sahko.tk/blob/master/parse.php
default_vat_multiplier = 1.24
nordpool_api_endpoint = 'http://www.nordpoolspot.com/api/marketdata/page/35?currency=,,EUR,EUR'


class SahkoCommand(ChatCommand):
    run_async = True  # Should be asynchronous

    def __init__(self):
        super().__init__(
            name='sahko',
            regex=regex_simple_command('sähkö'),
            help_text_short=('!sahko', 'Sähkön hinta')
        )
        self.dataset = None

    def is_enabled_in(self, chat):
        return True

    def handle_update(self, update: Update, context: CallbackContext = None):
        res: Response = requests.get(nordpool_api_endpoint)
        if res.status_code != 200:
            raise ConnectionError(f'Nordpool Api error. Request got res with status: {str(res.status_code)}')

        content: dict = res.json()
        data: dict = content.get('data')

        days: List[Day] = []
        for i in range(7):
            current_day = Day(i, [])
            for hour in range(24):
                day = data.get('Rows')[hour].get('Columns')[i].get('Name')
                if current_day.date is None:
                    current_day.date = datetime.datetime.strptime(day, '%d-%m-%Y').date()
                price = data.get('Rows')[hour].get('Columns')[i].get('Value')
                datapoint = Hour(hour, price)
                current_day.hours.append(datapoint)
            days.append(current_day)

        print('done!')


class Day:
    def __init__(self, weekday_index: int, hours: List['Hour']):
        """ Week day index starts at 0 """
        self.date: datetime.date = None
        self.weekday_index: int = weekday_index
        self.short_name: str = fi_short_day_name_from_day_index(weekday_index)
        self.hours: List[Hour] = hours or []

class Hour:
    def __init__(self, hour_index: int, price: float):
        """ Hour index starts at 0 """
        self.hour_index: int = hour_index
        self.price: float = price

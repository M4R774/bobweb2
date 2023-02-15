import datetime
import logging
from typing import List

import requests

from requests import Response

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob.command import ChatCommand, regex_simple_command

from bobweb.bob.utils_common import fi_short_day_name_from_day_index, has, fitzstr_from

logger = logging.getLogger(__name__)

#  Implementation is based on https://github.com/slehtonen/sahko.tk/blob/master/parse.php


class VatMultiplierPeriod:
    def __init__(self, start: datetime.date, end: datetime.date, vat_multiplier: float):
        self.start = start
        self.end = end
        self.vat_multiplier = vat_multiplier


default_price_scale = 0.1  # For some reason the prices need to be scaled by dividing with 10
vat_multiplier_default = 1.24
vat_multiplier_special_periods = [
    # From 1.12.2022 to 30.3.2023 VAT is temporarily lowered to 10 %
    VatMultiplierPeriod(start=datetime.date(2022, 12, 1), end=datetime.date(2023, 4, 30), vat_multiplier=1.1)
]

float_scale = 2
# Note: Nordpool times are in CET (UTC+1)
nordpool_date_format = '%d-%m-%Y'
nordpool_api_endpoint = 'http://www.nordpoolspot.com/api/marketdata/page/35?currency=,,EUR,EUR'
fetch_failed_msg = 'Sähkön hintojen haku epäonnistui 🔌✂️'


class SahkoCommand(ChatCommand):
    run_async = True  # Should be asynchronous

    def __init__(self):
        super().__init__(
            name='sahko',
            regex=regex_simple_command('s[aä]hk[oö]'),
            help_text_short=('!sahko', 'Sähkön hinta')
        )
        self.dataset = None

    def is_enabled_in(self, chat):
        return True

    def handle_update(self, update: Update, context: CallbackContext = None):
        # try:
        price_data = fetch_7_day_price_data()
        # except Exception as e:
        #     update.effective_chat.send_message(fetch_failed_msg)
        #     return

        todays_data = next((x for x in price_data if x.date == update.effective_message.date.date()), None)
        if has(todays_data):
            prices = [float(x.price) for x in todays_data.hours]
            avg: float = sum(prices) / len(prices)
            min_hour: HourPriceData = min(todays_data.hours)
            max_hour: HourPriceData = max(todays_data.hours)
            vat_str = get_vat_str(get_vat_by_date(update.effective_message.date.date()))
            todays_data_str = f'Pörssisähkö {fitzstr_from(update.effective_message.date)} ⚡ ' \
                              f'(sis. ALV {vat_str}%)\n' \
                              f'keski: {round(avg, float_scale)} snt\n' \
                              f'alin: {round(min_hour.price, float_scale)} snt, klo {min_hour.hour_range_str()}, \n' \
                              f'ylin: {round(max_hour.price, float_scale)} snt, klo {max_hour.hour_range_str()}'
        else:
            todays_data_str = 'Ei onnaa'

        update.effective_chat.send_message(todays_data_str)

#
##
### TODO: Nordicpool is CET, so hours need to be suffled accordingly
##
#

def fetch_7_day_price_data() -> List['DatePriceData']:
    res: Response = requests.get(nordpool_api_endpoint)
    if res.status_code != 200:
        raise ConnectionError(f'Nordpool Api error. Request got res with status: {str(res.status_code)}')

    content: dict = res.json()
    data: dict = content.get('data')

    price_data_list: List[DatePriceData] = []
    for i in range(7):
        current_date = None
        for hour in range(24):
            day = data.get('Rows')[hour].get('Columns')[i].get('Name')
            if current_date is None:
                date = datetime.datetime.strptime(day, nordpool_date_format).date()
                current_date = DatePriceData(date)

            price_str: str = data.get('Rows')[hour].get('Columns')[i].get('Value').replace(',', '.')
            price: float = float(price_str) * current_date.vat_multiplier * default_price_scale
            current_date.hours.append(HourPriceData(hour, price))
        price_data_list.append(current_date)

    return price_data_list


class DatePriceData:
    def __init__(self, date: datetime.date):
        self.date: datetime.date = date
        self.short_name_fi: str = fi_short_day_name_from_day_index(date.weekday())
        self.vat_multiplier = get_vat_by_date(date)
        self.hours: List[HourPriceData] = []


class HourPriceData:
    def __init__(self, hour_index: int, price: float):
        """ Hour index starts at 0 which equals to hour between 00:00 - 01:00 """
        self.hour_index: int = hour_index
        self.price: float = price

    def __lt__(self, other):
        return self.price < other.price

    def hour_range_str(self):
        return f'{get_zero_padded_int(self.hour_index)}:00 - {get_zero_padded_int(self.hour_index + 1)}:59'


def get_vat_by_date(date: datetime.date):
    for period in vat_multiplier_special_periods:
        if period.start <= date <= period.end:
            return period.vat_multiplier
    return vat_multiplier_default


def get_vat_str(vat_multiplier: float) -> str:
    """ 1.24 => 24 """
    return str(round((vat_multiplier - 1) * 100))


def get_zero_padded_int(number: int, min_length: int = 2):
    """ If numbers str presentation is shorter than min length,
    leading zeroes are added (padding) to match min length """
    return (min_length - len(str(number))) * '0' + str(number)

import asyncio
import datetime
import logging
import random
from typing import List, Optional, Dict

from telegram import Update
from telegram.ext import CallbackContext

from bobweb.bob import database, async_http, config

from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from bobweb.bob.message_board import MessageBoardMessage
from bobweb.web.bobapp.models import ChatMember

logger = logging.getLogger(__name__)

dictionary_of_weather_emojis = {
    'snow': '🌨 lumisadetta',
    'rain': '🌧 sadetta',
    'fog': '🌫 sumua',
    'smoke': '🌫 savua',
    'mist': '🌫 usvaa',
    'haze': '🌫 utua',
    'clear sky': '🌞 poutaa',
    'thunderstorm': '🌩 ukkosta',
    'few clouds': '☀ ☁ melkein selkeää',
    'scattered clouds': '☁ puolipilvistä',
    'broken clouds': '☁☁ melko pilvistä',
    'overcast clouds': '☁☁☁ pilvistä',
    'drizzle': '💧 tihkusadetta',
}


class WeatherData:
    """ Contains weather data for one update for a city """

    def __init__(self,
                 city_row: str,
                 time_row: str,
                 temperature_row: str,
                 wind_row: str,
                 weather_description_row: str,
                 sunrise_and_set_row: str):
        self.city_row = city_row
        self.time_row = time_row
        self.temperature_row = temperature_row
        self.wind_row = wind_row
        self.weather_description_row = weather_description_row
        self.sunrise_and_set_row = sunrise_and_set_row
        # Created at timestamp for when the weather date was created
        self.created_at = datetime.datetime.now()


class WeatherCommand(ChatCommand):
    """ Command that gives weather information for a given city
        or for the city that the user has previously requested. """

    def __init__(self):
        super().__init__(
            name='sää',
            regex=regex_simple_command_with_parameters('sää'),
            help_text_short=('!sää', '[kaupunki]:n sää')
        )

    def is_enabled_in(self, chat):
        return chat.weather_enabled

    async def handle_update(self, update: Update, context: CallbackContext = None):
        city_parameter = self.get_parameters(update.effective_message.text)
        chat_member: ChatMember = database.get_chat_member(chat_id=update.effective_chat.id,
                                                           tg_user_id=update.effective_user.id)

        city = city_parameter or chat_member.latest_weather_city
        if city:
            await send_weather_update_for_city(update, city_parameter, chat_member)
            return

        await update.effective_chat.send_message("Määrittele kaupunki kirjoittamalla se komennon perään.")


async def fetch_and_parse_weather_data(city_parameter) -> Optional[WeatherData]:
    base_url = "https://api.openweathermap.org/data/2.5/weather?"
    if config.open_weather_api_key is None:
        raise EnvironmentError("OPEN_WEATHER_API_KEY is not set.")

    params = {'appid': config.open_weather_api_key, 'q': city_parameter}
    content = await async_http.get_json(base_url, params=params)
    if content["cod"] == "404":
        return None  # city not found

    main = content["main"]
    wind = content["wind"]
    sys = content["sys"]
    weather = content["weather"]
    offset = 127397  # country codes start here in unicode list order
    country = chr(ord(sys["country"][0]) + offset) + chr(ord(sys["country"][1]) + offset)
    city_name = content["name"]

    delta = datetime.timedelta(seconds=content["timezone"])
    timezone = datetime.timezone(delta)
    localtime = datetime.datetime.utcnow() + delta

    current_temperature = round(main["temp"] - 273.15, 1)  # kelvin to celsius
    current_feels_like = round(main["feels_like"] - 273.15, 1)  # kelvin to celsius

    current_wind = wind["speed"]
    current_wind_direction = wind_direction(wind['deg'])

    weather_description_raw = weather[0]["description"]
    weather_description = dictionary_of_weather_emojis.get(weather_description_raw, weather_description_raw)

    sunrise_localtime = datetime.datetime.utcfromtimestamp(sys['sunrise']) + delta
    sunset_localtime = datetime.datetime.utcfromtimestamp(sys['sunset']) + delta

    return WeatherData(
        city_row=f"{country} {city_name}",
        time_row=f"🕒 {localtime.strftime('%H:%M')} ({timezone})",
        temperature_row=f"🌡 {current_temperature} °C (tuntuu {current_feels_like} °C)",
        wind_row=f"💨 {current_wind} m/s {current_wind_direction}",
        weather_description_row=str(weather_description),
        sunrise_and_set_row=f"🌅 auringon nousu {sunrise_localtime.strftime('%H:%M')} 🌃 lasku {sunset_localtime.strftime('%H:%M')}"
    )


async def send_weather_update_for_city(update: Update, city: str, chat_member: ChatMember) -> None:
    data: Optional[WeatherData] = await fetch_and_parse_weather_data(city)
    if data:
        chat_member.latest_weather_city = city
        chat_member.save()
        reply_text = format_weather_command_reply_text(data)
    else:
        reply_text = "Kaupunkia ei löydy."
    await update.effective_chat.send_message(reply_text)


def wind_direction(degrees):
    directions = ['pohjoisesta', 'koillisesta', 'idästä', 'kaakosta', 'etelästä', 'lounaasta', 'lännestä', 'luoteesta']
    cardinal = round(degrees / (360 / len(directions)))
    return directions[cardinal % len(directions)]


def format_weather_command_reply_text(weather_data: WeatherData) -> str:
    return (f"{weather_data.city_row}\n"
            f"{weather_data.time_row}\n"
            f"{weather_data.temperature_row}\n"
            f"{weather_data.wind_row}\n"
            f"{weather_data.weather_description_row}")


def format_scheduled_message_preview(weather_data: WeatherData) -> str:
    """ Returns a preview of the scheduled message that is shown in the pinned message section on top of the
        chat content window. Does not have time and wind is set as the last item. """
    return (f"{weather_data.city_row}\n"
            f"{weather_data.time_row}\n"
            f"{weather_data.temperature_row}\n"
            f"{weather_data.weather_description_row}\n"
            f"{weather_data.wind_row}\n"
            f"{weather_data.sunrise_and_set_row}")


def format_scheduled_message_body(weather_data: WeatherData) -> str:
    """ Creates body for a single city text item in the scheduled message. Contains extra info not in the preview """
    return ""


async def create_weather_scheduled_message(chat_id) -> 'WeatherMessageBoardMessage':
    message = WeatherMessageBoardMessage(chat_id)
    await message.change_city_and_start_update_loop()
    return message


class WeatherMessageBoardMessage(MessageBoardMessage):
    """
    Scheduled message for the weather. Extends MessageBoardMessage by adding internal logic that iterates through the list
    of cities that have been requested by the members of the chat in the chat. Weather data for each city is saved in
    cache that is refreshed every hour that the scheduled message is active. City weather data is lazy evaluated when
    required so that they are not fetched unnecessarily.
    """
    city_change_delay_in_seconds = 60

    def __init__(self, chat_id: int):
        # Fetch cities from the database, suffle them and start the action
        self.cities: List[str] = list(database.get_latest_weather_city_for_members_of_chat(chat_id))

        if not self.cities:
            super().__init__(message="Esikatselu säästä", preview="")
            return

        random.shuffle(self.cities)  # NOSONAR

        self.weather_cache: Dict[str, WeatherData] = {}
        self.weather_cache_updated_at = None

        # self.initiate_cache(cities)
        # self.cities_with_data = [key for (key, value) in self.weather_cache]

        self.current_city_index = -1
        super().__init__(
            message="Säädiedotukset tulevat tähän",
            preview="Esikatselu säästä"
        )

    async def change_city_and_start_update_loop(self):
        # Initial weather change
        await self.change_city()
        # Start weather change loop. Once a minute city is changes if there are multiple cities
        while len(self.cities) > 1:
            # Sleep for defined delay and then change city
            await asyncio.sleep(WeatherMessageBoardMessage.city_change_delay_in_seconds)
            await self.change_city()

    async def change_city(self):
        if not self.cities:
            return  # No cities

        # Update index. Either next index or first if last item of the list
        if self.current_city_index < len(self.cities) - 1:
            self.current_city_index += 1
        else:
            self.current_city_index = 0

        current_city = self.cities[self.current_city_index]
        weather_data: Optional[WeatherData] = await self.find_weather_data(current_city)
        self.preview = format_scheduled_message_preview(weather_data)
        self.message = format_scheduled_message_body(weather_data)

        await self.message_board.set_scheduled_message(self)

    async def initiate_cache(self, cities: List[str]) -> None:
        for city in cities:
            data: Optional[WeatherData] = await fetch_and_parse_weather_data(city)
            if data:
                self.weather_cache[city] = data
        self.weather_cache_updated_at = datetime.datetime.now()

    async def find_weather_data(self, city_name: str) -> Optional[WeatherData]:
        # If there is cached weather data that was created less than an hour ago, return it. Else, fetch new data from
        # the weather api, parse it and add it to the cache.
        now = datetime.datetime.now()
        cached_item = self.weather_cache.get(city_name, None)
        if cached_item and cached_item.created_at + datetime.timedelta(hours=1) > now:
            return cached_item
        else:
            data: Optional[WeatherData] = await fetch_and_parse_weather_data(city_name)
            if data:
                self.weather_cache[city_name] = data
            return data

import datetime
import logging
import os

import requests
from telegram import Update
from telegram.ext import CallbackContext

import database


logger = logging.getLogger(__name__)


def weather_command(update: Update, context: CallbackContext = None):
    city_parameter = update.message.text.replace(update.message.text.split()[0], "").lstrip()
    if city_parameter != "":
        reply_text = fetch_and_format_weather_data(city_parameter)
        if reply_text is not None:
            chat_member = database.get_chat_member(chat_id=update.effective_chat.id,
                                                   tg_user_id=update.effective_user.id)
            chat_member.latest_weather_city = city_parameter
            chat_member.save()
    else:
        chat_member = database.get_chat_member(chat_id=update.effective_chat.id,
                                               tg_user_id=update.effective_user.id)
        if chat_member.latest_weather_city is not None:
            reply_text = fetch_and_format_weather_data(chat_member.latest_weather_city)
        else:
            reply_text = "Määrittele kaupunki kirjoittamalla se komennon perään. "
    update.message.reply_text(reply_text, quote=False)


def fetch_and_format_weather_data(city_parameter):
    base_url = "https://api.openweathermap.org/data/2.5/weather?"
    if os.getenv("OPEN_WEATHER_API_KEY") is None:
        logger.error("OPEN_WEATHER_API_KEY is not set.")
        raise EnvironmentError
    complete_url = base_url + "appid=" + os.getenv("OPEN_WEATHER_API_KEY") + "&q=" + city_parameter
    response = requests.get(complete_url)
    x = response.json()
    if x["cod"] != "404":
        y = x["main"]
        w = x["wind"]
        s = x["sys"]
        z = x["weather"]
        offset = 127397  # country codes start here in unicode list order
        country = chr(ord(s["country"][0]) + offset) + chr(ord(s["country"][1]) + offset)
        delta = datetime.timedelta(seconds=x["timezone"])
        timezone = datetime.timezone(delta)
        localtime = datetime.datetime.utcnow() + delta
        current_temperature = round(y["temp"] - 273.15, 1)  # kelvin to celsius
        current_feels_like = round(y["feels_like"] - 273.15, 1)  # kelvin to celsius
        current_wind = w["speed"]
        current_wind_direction = wind_direction(w['deg'])
        weather_description = replace_weather_description_with_emojis(z[0]["description"])
        weather_string = (country + " " + city_parameter +
                          "\n🕒 " + localtime.strftime("%H:%M (") + str(timezone) + ")" +
                          "\n🌡 " + str(current_temperature) + " °C (tuntuu " + str(current_feels_like) + " °C)"
                          "\n💨 " + str(current_wind) + " m/s " + str(current_wind_direction) +
                          "\n" + str(weather_description))
        reply_text = weather_string
    else:
        reply_text = "Kaupunkia ei löydy."
    return reply_text


def replace_weather_description_with_emojis(description):
    dictionary_of_weather_emojis = {
        'snow': ['lumisadetta', '🌨'],
        'rain': ['sadetta', '🌧'],
        'fog': ['sumua', '🌫'],
        'smoke': ['savua', '🌫'],
        'mist': ['usvaa', '🌫'],
        'haze': ['utua', '🌫'],
        'clear sky': ['poutaa', '🌞'],
        'thunderstorm': ['ukkosta', '🌩'],
        'few clouds': ['melkein selkeää', '☀ ☁'],
        'scattered clouds': ['puolipilvistä', '☁'],
        'broken clouds': ['melko pilvistä', '☁☁'],
        'overcast clouds': ['pilvistä', '☁☁☁'],
        'drizzle': ['tihkusadetta', '💧']
    }
    for i, j in dictionary_of_weather_emojis.items():
        if i in description:
            description = j[1] + " " + j[0]
    return description


def wind_direction(degrees):
    directions = ['pohjoisesta', 'koillisesta', 'idästä', 'kaakosta', 'etelästä', 'lounaasta', 'lännestä', 'luoteesta']
    cardinal = round(degrees / (360 / len(directions)))
    return directions[cardinal % len(directions)]

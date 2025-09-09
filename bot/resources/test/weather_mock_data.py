helsinki_weather = {
    "coord": {"lon": 24.9355, "lat": 60.1695},
    "weather": [
        {"id": 601, "main": "Snow", "description": "snow", "icon": "13n"}
    ],
    "base": "stations",
    "main": {
        "temp": 272.52,
        "feels_like": 270.24,
        "temp_min": 271.6,
        "temp_max": 273.6,
        "pressure": 977,
        "humidity": 90
    },
    "visibility": 1100,
    "wind": {"speed": 1.79, "deg": 225, "gust": 5.36},
    "snow": {"1h": 0.49},
    "clouds": {"all": 100},
    "dt": 1643483100,
    "sys": {
        "type": 2,
        "id": 2028456,
        "country": "FI",
        "sunrise": 1643438553,
        "sunset": 1643466237
    },
    "timezone": 7200,
    "id": 658225,
    "name": "Helsinki",
    "cod": 200
}

turku_weather = helsinki_weather.copy()
turku_weather['name'] = 'tää on Turku'


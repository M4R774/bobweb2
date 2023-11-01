import logging
import os

logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=logging_format, level=logging.INFO)  # NOSONAR

# Set httpx logging to only include warning level logs.
# Otherwise, logs telegram api update checks
logging.getLogger("httpx").setLevel(logging.WARNING)

# Remember to add your values to the environment variables
# Required to run the bot
bot_token = os.getenv("BOT_TOKEN")

# OpenAi Api key. Required for OpenAiApi related functionalities (Gpt, Dalle2, Transcribe)
openai_api_key = os.getenv('OPENAI_API_KEY')

# Required for WeatherCommand
open_weather_api_key = os.getenv('OPEN_WEATHER_API_KEY')

# Required in production, optional while developing.
# Required only for some functionalities (GptCommand)
api_id = os.getenv("TG_CLIENT_API_ID")
api_hash = os.getenv("TG_CLIENT_API_HASH")

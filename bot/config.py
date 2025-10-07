import logging
import os
import sys

from dotenv import load_dotenv, find_dotenv

# Load .env file from project root if present. Do not override existing environment variables.
_dotenv_path = find_dotenv(usecwd=True)
if _dotenv_path:
    load_dotenv(dotenv_path=_dotenv_path, override=False)

# Set root level logging
logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=logging_format, level=logging.INFO)  # NOSONAR

# Enable chat event logger if environment variable is set to true
chat_event_logger_level = os.getenv("CHAT_EVENT_LOGGER_LEVEL", '').lower() == 'true'

# Set httpx and asyncio logging to only include warning level logs.
# Otherwise, logs telegram api update checks
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# Set higher logging level for scheduler so that each update is not logged
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)

if len(sys.argv) > 1 and sys.argv[1] == 'test':
    logging.disable(logging.DEBUG)

# Remember to add your values to the environment variables
# Required to run the bot
bot_token = os.getenv("BOT_TOKEN")

# OpenAi Api key. Required for OpenAiApi related functionalities (Gpt, Dalle2, Transcribe)
openai_api_key = os.getenv('OPENAI_API_KEY')

# Gemini Api key. Required for Gpt
gemini_api_key = os.getenv('GEMINI_API_KEY')

# Required for WeatherCommand
open_weather_api_key = os.getenv('OPEN_WEATHER_API_KEY')

# Required for electricity price functionalities
entsoe_api_key = os.getenv('ENTSOE_API_KEY')

# Twitch client API key and secret. Required for Twitch integration.
twitch_client_api_id = os.getenv('TWITCH_CLIENT_ID')
twitch_client_api_secret = os.getenv('TWITCH_CLIENT_SECRET')

# Required in production, optional while developing.
# Required only for some functionalities (GptCommand when reply chain has more than 1 message)
tg_client_api_id = os.getenv("TG_CLIENT_API_ID")
tg_client_api_hash = os.getenv("TG_CLIENT_API_HASH")

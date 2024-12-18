import logging
import os

# Set root level logging
logging_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=logging_format, level=logging.INFO)  # NOSONAR

# Set httpx and asyncio logging to only include warning level logs.
# Otherwise, logs telegram api update checks
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# Set higher logging level for scheduler so that each update is not logged
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)

# Remember to add your values to the environment variables
# Required to run the bot
bot_token = os.getenv("BOT_TOKEN")

# OpenAi Api key. Required for OpenAiApi related functionalities (Gpt, Dalle2, Transcribe)
openai_api_key = os.getenv('OPENAI_API_KEY')

# Required for WeatherCommand
open_weather_api_key = os.getenv('OPEN_WEATHER_API_KEY')

# Required for electricity price functionalities
entsoe_api_key = os.getenv('ENTSOE_API_KEY')

# Twitch client API key and secret. Required for Twitch integration.
twitch_client_api_id = os.getenv('TWITCH_CLIENT_ID')
twitch_client_api_secret = os.getenv('TWITCH_CLIENT_SECRET')
twitch_api_access_token_env_var_name = 'TWITCH_API_ACCESS_TOKEN'

# Required in production, optional while developing.
# Required only for some functionalities (GptCommand when reply chain has more than 1 message)
tg_client_api_id = os.getenv("TG_CLIENT_API_ID")
tg_client_api_hash = os.getenv("TG_CLIENT_API_HASH")

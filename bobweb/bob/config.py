import os

# Remember to add your values to the environment variables
# Required to run the bot
bot_token = os.getenv("BOT_TOKEN")

# Required in production, optional while developing.
# Required only for some functionalities (GptCommand)
api_id = os.getenv("TG_CLIENT_API_ID")
api_hash = os.getenv("TG_CLIENT_API_HASH")

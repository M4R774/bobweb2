import main
import database

async def create(bot):
    with open('../web/db.sqlite3', 'rb') as database_file:
        await main.send_file_to_global_admin(database_file, bot)

import main


async def create(bot):
    with open('bobweb/web/db.sqlite3', 'rb') as database_file:
        await main.send_file_to_global_admin(database_file, bot)

from bot import broadcaster


async def create(bot):
    with open('web/db.sqlite3', 'rb') as database_file:  # NOSONAR (S7493)
        await broadcaster.send_file_to_global_admin(database_file, bot)

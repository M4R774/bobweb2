import datetime
import os
import re

from telegram import Bot, MessageEntity, Update

from bobweb.bob import database
from bobweb.bob.broadcaster import broadcast
from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.ranks import promote


async def broadcast_and_promote(bot: Bot):
    bob_db_object = database.get_the_bob()
    broadcast_message = os.getenv("COMMIT_MESSAGE")
    if broadcast_message != bob_db_object.latest_startup_broadcast_message and broadcast_message != "":
        bob_db_object.latest_startup_broadcast_message = broadcast_message
        bob_db_object.save()
        await broadcast(bot, broadcast_message)
        await promote_committer_or_find_out_who_he_is(bot)
    else:
        await broadcast(bot, "Olin vain hiljaa hetken. ")


async def promote_committer_or_find_out_who_he_is(bot: Bot):
    commit_author_email, commit_author_name, git_user = get_git_user_and_commit_info()

    if git_user.tg_user is not None:
        await promote_or_praise(git_user, bot)
    else:
        reply_message = "Git käyttäjä " + str(commit_author_name) + " " + str(commit_author_email) + \
                        " ei ole minulle tuttu. Onko hän joku tästä ryhmästä?"
        await broadcast(bot, reply_message)


def get_git_user_and_commit_info():
    commit_author_name = os.getenv("COMMIT_AUTHOR_NAME", "You should not see this")
    commit_author_email = os.getenv("COMMIT_AUTHOR_EMAIL", "You should not see this")
    git_user = database.get_git_user(commit_author_name, commit_author_email)
    return commit_author_email, commit_author_name, git_user


async def promote_or_praise(git_user, bot):
    now = datetime.datetime.now(fitz)
    tg_user = database.get_telegram_user(user_id=git_user.tg_user.id)

    if tg_user.latest_promotion_from_git_commit is None or \
            tg_user.latest_promotion_from_git_commit < now.date() - datetime.timedelta(days=6):
        committer_chat_memberships = database.get_chat_memberships_for_user(tg_user=git_user.tg_user)
        for membership in committer_chat_memberships:
            promote(membership)
        tg_user.latest_promotion_from_git_commit = now.date()
        tg_user.save()
        await broadcast(bot, str(git_user.tg_user) + " ansaitsi ylennyksen ahkeralla työllä. ")
    else:
        # It has not been week yet since last promotion
        await broadcast(bot, "Kiitos " + str(git_user.tg_user) + ", hyvää työtä!")


async def process_entities(update):
    global_admin = database.get_global_admin()
    if global_admin is not None:
        if update.effective_user.id == global_admin.id:
            for message_entity in update.effective_message.entities:
                await process_entity(message_entity, update)
        else:
            await update.effective_message.reply_text("Et oo vissiin global_admin?")
    else:
        await update.effective_message.reply_text("Globaalia adminia ei ole asetettu.")


async def process_entity(message_entity: MessageEntity, update: Update):
    _, commit_author_name, git_user = get_git_user_and_commit_info()
    if message_entity.type == "text_mention":
        user = database.get_telegram_user(message_entity.user.id)
        git_user.tg_user = user
    elif message_entity.type == "mention":
        username = re.search('@(.*)', update.effective_message.text)
        telegram_users = database.get_telegram_user_by_name(str(username.group(1)).strip())

        if telegram_users.count() > 0:
            git_user.tg_user = telegram_users[0]
        else:
            await update.effective_message.reply_text("En löytänyt tietokannastani ketään tuon nimistä.")
    git_user.save()
    await promote_or_praise(git_user, update.effective_message.via_bot)

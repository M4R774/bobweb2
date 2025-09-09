# Messages that are used by multiple modules. Here to prevent circular module initialization problem
from telegram import Update

from bot.utils_common import has


def get_daily_question_notification(update: Update, winner_set: bool) -> str:
    if has(update.edited_message):
        return dq_created_from_msg_edit(winner_set)
    else:
        return dq_saved_msg(winner_set)


def dq_saved_msg(winner_set: bool) -> str:
    return f'Kysymys {and_winner_saved_msg if winner_set else ""}tallennettu'


def dq_created_from_msg_edit(winner_set: bool) -> str:
    return f'Kysymys {and_winner_saved_msg if winner_set else ""}tallennettu jälkikäteen lisätyn \'#päivänkysymys\' ' \
           'tägin myötä. Muokkausta edeltäviä viestejä ei ole tallennettu vastauksiksi ' \
           'ja ne tulisi merkitä \'\\vastaus\'-komennolla'


and_winner_saved_msg = 'ja edellisen kysymyksen voittaja '

# Messages that are used by multiple modules. Here to prevent circular module initialization problem
def dq_saved_msg(winner_set) -> str:
    return f'Kysymys {and_winner_saved_msg if winner_set else ""}tallennettu'


def dq_created_from_msg_edit(winner_set) -> str:
    return f'Kysymys {and_winner_saved_msg if winner_set else ""}tallennettu jälkikäteen lisätyn \'#päivänkysymys\' ' \
           'tägin myötä. Muokkausta edeltäviä vastauksia ei ole tallennettu vastauksiksi'


and_winner_saved_msg = 'ja edellisen kysymyksen voittaja '

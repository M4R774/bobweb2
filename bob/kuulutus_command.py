from abstract_command import AbstractCommand
from bob.constants import PREFIXES_MATCHER
import database


class KuulutusCommand(AbstractCommand):
    def __init__(self):
        super().__init__(
            'kuulutus',
            r'' + PREFIXES_MATCHER + 'kuulutus',
            ('!kuulutus', '[on|off]')
        )

    def handle_update(self, update):
        broadcast_toggle_command(update)

    def is_enabled_in(self, chat):
        return chat.broadcast_enabled


def broadcast_toggle_command(update):
    chat = database.get_chat(chat_id=update.effective_chat.id)
    if update.message.text.casefold() == "/kuulutus on".casefold():
        chat.broadcast_enabled = True
        update.message.reply_text("Kuulutukset ovat nyt päällä tässä ryhmässä.", quote=False)
    elif update.message.text.casefold() == "/kuulutus off".casefold():
        chat.broadcast_enabled = False
        update.message.reply_text("Kuulutukset ovat nyt pois päältä.", quote=False)
    else:
        update.message.reply_text("Käyttö: \n"
                                  "'/kuulutus on' - Kytkee kuulutukset päälle \n"
                                  "'/kuulutus off' - Kytkee kuulutukset pois päältä\n")
        if chat.broadcast_enabled:
            update.message.reply_text("Tällä hetkellä kuulutukset ovat päällä.", quote=False)
        else:
            update.message.reply_text("Tällä hetkellä kuulutukset ovat pois päältä.", quote=False)
    chat.save()

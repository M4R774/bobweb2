from telegram.ext import CallbackContext

from abstract_command import AbstractCommand
from bob_constants import PREFIXES_MATCHER
import database
from telegram import Update


class UsersCommand(AbstractCommand):
    def __init__(self):
        super().__init__(
            name='käyttäjät',
            regex=r'' + PREFIXES_MATCHER + 'käyttäjät',
            help_text_short=('!käyttäjät', 'Lista käyttäjistä')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        users_command(update)

    def is_enabled_in(self, chat):
        return True


def users_command(update: Update):
    chat_members = database.get_chat_members_for_chat(chat_id=update.effective_chat.id)
    reply_text = ""
    # code in place if we want to get the chat name and use it
    # chat_name = str(update.effective_chat.title)
    # if chat_name != "None":
    #    reply_text = chat_name + " -ryhmän käyttäjät " + "\U0001F913 " + "\n" + "\n"
    # else:
    #    reply_text = "Käyttäjät " + "\U0001F913 " + "\n" + "\n"
    reply_text = "*Käyttäjät* " + "\U0001F913 " + "\n" + "\n" + \
                 "*Nimi* ⌇ Arvo ⌇ Kunnia ⌇ Viestit" + "\n"  # nerd face emoji
    for chat_member in chat_members:
        # member_name = re.match(r'^.*(?=@)', str(chat_member))  # from start till '@'
        # reply_text += "*" + member_name[0] + " ⌇*" + " " + \
        reply_text += "*" + str(chat_member) + " ⌇*" + " " + \
                      str(chat_member.rank) + " ⌇ " + \
                      str(chat_member.prestige) + " ⌇ " + \
                      str(chat_member.message_count) + "\n"
    update.message.reply_markdown(reply_text, quote=False)

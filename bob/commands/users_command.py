import sys
from typing import List

from telegram.ext import CallbackContext
from telegram import Update

sys.path.append('../')  # needed for sibling import
from format_utils import MessageArrayFormatter
from chat_command import ChatCommand
from bob_constants import PREFIXES_MATCHER
import database

sys.path.append('../web')  # needed for sibling import
from bobapp.models import ChatMember


class UsersCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='käyttäjät',
            regex=r'^' + PREFIXES_MATCHER + 'käyttäjät$',  # '^' = Start of string, '$' = end of sting
            help_text_short=('!käyttäjät', 'Lista käyttäjistä')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        users_command(update)

    def is_enabled_in(self, chat):
        return True


def users_command(update: Update):
    chat_members: List[ChatMember] = database.get_chat_members_for_chat(chat_id=update.effective_chat.id)
    chat_members = exclude_possible_bots(chat_members)

    headings = ['Nimi', 'A', 'K', 'V']
    # First make list of rows. Each row is single users data
    member_array = create_member_array(chat_members)
    member_array.insert(0, headings)

    formatter = MessageArrayFormatter('⌇ ', '=', ).with_truncation(28, 0)
    formatted_members_array_str = formatter.format(member_array)

    footer = 'A=Arvo, K=Kunnia, V=Viestit'

    reply_text = '```\n' \
                 + 'Käyttäjät \U0001F913\n\n' \
                 + f'{formatted_members_array_str}\n' \
                 + f'{footer}' \
                 + '```'  # '\U0001F913' => nerd emoji, '```' =>  markdown code block

    update.message.reply_markdown(reply_text, quote=False)


def exclude_possible_bots(members: List[ChatMember]):
    return [member for member in members if not str(member.tg_user).lower().endswith('bot')]


def create_member_array(chat_members: List[ChatMember]):
    array_of_users = []
    for member in chat_members:
        user_row = [str(member.tg_user), member.rank, member.prestige, member.message_count]
        array_of_users.append(user_row)

    # Sort users descending in order of rank, prestige, message_count
    array_of_users.sort(key=lambda row: (-row[1], -row[2], -row[3]))
    return array_of_users

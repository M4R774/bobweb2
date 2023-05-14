from typing import TYPE_CHECKING, Union

from telegram import Message

from bobweb.bob.tests_msg_btn_utils import button_labels_from_reply_markup
from bobweb.bob.utils_common import split_to_chunks
from bobweb.bob.utils_format import Align, fit_text, form_single_item_with_padding

if TYPE_CHECKING:
    from bobweb.bob.tests_mocks_v2 import MockMessage

"""
Chat log printer for tests (WIP)
- Tries to mimick real Telegram chat client with look and content
- Users' messages are on the left side of the console and bot's on the right side
- Makes creating tests fast, as the result can be seen as it would be in the telegram client
"""

message_time_format = '%d.%m.%Y %H.%M.%S'
message_id_limit = 3
username_limit = 5
line_width_limit = 80
message_width_limit = 60
reply_msg_preview_limit = 25
tab_width = 3


def print_msg(msg: 'MockMessage', is_edit=False):
    """
    Prints single message-event to the console. If message is reply, main attributes of it's
    target message is displayd. If message is editted, its new content is printed with "Edited" flair

    :param msg: MockMessage object to print
    :param is_edit: true, if message has been edited
    """
    align = Align.RIGHT if msg.from_user.is_bot else Align.LEFT
    padding_width = line_width_limit - message_width_limit
    padding_left = 0 if align == align.LEFT else padding_width
    pad = padding_left * ' '

    header = pad + __msg_header(msg)
    reply_line = ''
    if msg.reply_to_message is not None:
        reply_line = pad + __reply_to_line(msg.reply_to_message) + '\n'

    formatted_text = __tabulated_msg_body(msg.text, align)
    buttons = __buttons_row(msg, pad)
    console_msg = (pad + 'EDITED MESSAGE\n' if is_edit else '') + \
                  f'{header}\n' \
                  f'{reply_line}' \
                  f'{formatted_text}\n' \
                  f'{buttons}' \
                  f'{line_width_limit * "-"}'
    print(console_msg)


def __msg_header(msg: 'MockMessage'):
    formatted_time = msg.date.strftime(message_time_format)
    chat_type = 'bot' if msg.from_user.is_bot else 'user'
    username = msg.from_user.username[:username_limit]
    return f'{str(msg.message_id)}. {chat_type} {username} at {formatted_time} in chat {msg.chat.id}'


def __reply_to_line(reply_to_message: Union['MockMessage', Message]):
    msg_id = reply_to_message.message_id
    username = reply_to_message.from_user.username[:username_limit]
    if reply_to_message.text:
        end_ellipsis = '...' if len(reply_to_message.text) > reply_msg_preview_limit else ''
        text = reply_to_message.text[:reply_msg_preview_limit] + end_ellipsis
    else:
        text = '[No text content in msg]'
    return f'reply to: ({msg_id}|{username}|"{text}")'


def __tabulated_msg_body(text, align: Align):
    padding_width = 0 if align == align.LEFT else line_width_limit - message_width_limit
    padding_left = padding_width * ' '
    line_change = '../'
    rows = text.split('\n')
    all_rows = []
    for i, r in enumerate(rows):
        if 'tulee ensin luoda uusi ky' in r:
            pass

        if len(r) <= line_width_limit:
            all_rows.append(r)
        else:

            chunks = split_to_chunks(r, message_width_limit - len(line_change))
            for j, chunk in enumerate(chunks):
                line_end = line_change if j < len(chunks) - 1 else ''
                all_rows.append(chunk + line_end)

    result = ''
    for i, r in enumerate(all_rows):
        first_c = '"' if i == 0 else ' '
        last_item = i == len(all_rows) - 1
        last_c = '"' if last_item else ' '
        result += padding_left + first_c + r + last_c + ('' if last_item else '\n')

    return result


def __buttons_row(msg: 'MockMessage', padding: str):
    if msg is None or msg.reply_markup is None:
        return ''
    return padding + str(button_labels_from_reply_markup(msg.reply_markup)) + '\n'


def __user_join_notification(username: str):
    content = f'user {fit_text(username, username_limit)} joined chat'
    return form_single_item_with_padding(content, line_width_limit, Align.CENTER)


def __add_line_changes_if_too_long(text: str, n: int, char: str):
    result = ""
    for i, c in enumerate(text):
        result += c
        if (i + 1) % n == 0:
            result += char
    return result

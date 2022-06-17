import os
import sys
from datetime import datetime

sys.path.append('../web')  # needed for sibling import
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)

django.setup()
from bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser


def get_the_bob():
    try:
        return Bob.objects.get(id=1)
    except Bob.DoesNotExist:
        return Bob(id=1, uptime_started_date=datetime.now())


def get_global_admin():
    return Bob.objects.get(id=1).global_admin


def get_chats():
    return Chat.objects.all()


def get_chat(chat_id, title=None):
    if Chat.objects.filter(id=chat_id).count() <= 0:
        chat = Chat(id=chat_id)
        if int(chat_id) < 0:
            chat.title = title
        chat.save()
        return chat
    else:
        return Chat.objects.get(id=chat_id)


def get_telegram_user(user_id):
    telegram_users = TelegramUser.objects.filter(id=user_id)
    if telegram_users.count() == 0:
        telegram_user = TelegramUser(id=user_id)
        telegram_user.save()
    else:
        telegram_user = TelegramUser.objects.get(id=user_id)
    return telegram_user


def increment_chat_member_message_count(chat_id, user_id):
    chat_members = ChatMember.objects.filter(chat=chat_id,
                                             tg_user=user_id)
    if chat_members.count() == 0:
        chat_member = ChatMember(chat=Chat.objects.get(id=chat_id),
                                 tg_user=TelegramUser.objects.get(id=user_id),
                                 message_count=1)
    else:
        chat_member = chat_members[0]
        chat_member.message_count += 1
    chat_member.save()


def get_telegram_user_by_name(username):
    return TelegramUser.objects.filter(username=username)


def get_chat_member(chat_id, tg_user_id):
    return ChatMember.objects.get(chat=chat_id,
                                  tg_user=tg_user_id)


def get_chat_members_for_chat(chat_id):
    return ChatMember.objects.filter(chat=chat_id)


def get_chat_memberships_for_user(tg_user):
    return ChatMember.objects.filter(tg_user=tg_user)


def get_git_user(commit_author_name, commit_author_email):
    if GitUser.objects.filter(name=commit_author_name, email=commit_author_email).count() <= 0:
        git_user = GitUser(name=commit_author_name, email=commit_author_email)
        git_user.save()
        return git_user
    else:
        return GitUser.objects.get(name=commit_author_name, email=commit_author_email)

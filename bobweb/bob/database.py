import os
import sys
from datetime import datetime

from django.core.exceptions import MultipleObjectsReturned
from django.db.models import QuerySet
from telegram import Update

sys.path.append('../web')  # needed for sibling import
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)

django.setup()
from bobweb.web.bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser,  DailyQuestionSeason, DailyQuestion


def has(querySet: QuerySet) -> bool:
    return querySet.count() > 0


def has_one(querySet: QuerySet) -> bool:
    return querySet.count() == 1


def has_no(querySet: QuerySet) -> bool:
    return querySet.count() == 0


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


def update_chat_in_db(update):
    if update.effective_chat.id < 0:
        title = update.effective_chat.title
    else:
        title = None
    get_chat(update.effective_chat.id, title)


def update_user_in_db(update):
    updated_user = get_telegram_user(update.effective_user.id)
    if update.effective_user.first_name is not None:
        updated_user.first_name = update.effective_user.first_name
    if update.effective_user.last_name is not None:
        updated_user.last_name = update.effective_user.last_name
    if update.effective_user.username is not None:
        updated_user.username = update.effective_user.username
    updated_user.save()
    increment_chat_member_message_count(update.effective_chat.id, update.effective_user.id)


# ########################## Daily Question ########################################
def save_daily_question(update: Update, season: DailyQuestionSeason) -> int:
    daily_question = DailyQuestion(season=season,
                                   date=datetime.today().date(),
                                   update_id=update.update_id,
                                   content=update.message.text,
                                   reply_count=0)
    daily_question.save()
    return daily_question.id


def is_first_daily_question_in_chat(update: Update) -> bool:
    return get_todays_question(update).count() == 0


def get_todays_question(update: Update) -> QuerySet:
    todays_question_set: QuerySet = DailyQuestion.objects.filter(
        season__chat=update.effective_chat.id,
        date=datetime.today())
    return todays_question_set


# ########################## Daily Question ########################################
def save_daily_question_season(update: Update, season_number=1, start_date=None) -> int:
    date = start_date if start_date is not None else update.message.date
    chat = get_chat(update.effective_chat.id)
    season = DailyQuestionSeason(chat=chat,
                                 season_number=season_number,
                                 start_date=date)
    season.save()
    return season.id


def get_daily_question_season(update: Update) -> QuerySet:
    date: datetime.date = update.message.date
    active_season_query: QuerySet = DailyQuestionSeason.objects.filter(
        chat=update.effective_chat.id,
        start_date__lte=date,
        end_date=None)
    return active_season_query

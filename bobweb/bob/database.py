import os
import sys
from datetime import datetime, timedelta

from django.core.exceptions import MultipleObjectsReturned
from django.db.models import QuerySet, Q
from telegram import Update

from bobweb.bob.utils_common import has, has_no

sys.path.append('../web')  # needed for sibling import
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "bobweb.web.web.settings"
)

django.setup()
from bobweb.web.bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser, DailyQuestionSeason, DailyQuestion, \
    DailyQuestionAnswer


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


def get_telegram_user(user_id) -> TelegramUser:
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
    question_author = get_telegram_user(update.effective_user.id)
    daily_question = DailyQuestion(season=season,
                                   datetime=update.message.date,
                                   update_id=update.update_id,
                                   question_author=question_author,
                                   content=update.message.text)
    daily_question.save()
    return daily_question.id


def find_all_questions_on_season(chat_id: int, target_datetime: datetime) -> QuerySet:
    return DailyQuestion.objects.filter(
        season__chat=chat_id,
        season__start_datetime__lte=target_datetime)\
        .filter(Q(season__end_datetime=None) | Q(season__end_datetime__gte=target_datetime))


def is_first_dq_in_season(update: Update) -> bool:
    return find_all_questions_on_season(update.effective_chat.id, update.message.date).count() == 0


def find_question_on_date(chat_id: int, target_datetime: datetime) -> QuerySet:
    todays_question_set: QuerySet = DailyQuestion.objects.filter(
        season__chat=chat_id,
        datetime__date=target_datetime.date())
    return todays_question_set


def find_dq_on_current_season(chat_id: int, target_datetime: datetime) -> QuerySet:
    latest_question_query: QuerySet = DailyQuestion.objects.filter(
        datetime__lt=target_datetime,
        season__isnull=False,
        season__chat=chat_id,
        season__start_datetime__lte=target_datetime,
        season__end_datetime=None) \
        .order_by('-datetime')
    return latest_question_query


def find_prev_daily_question_author_id(chat_id: int, target_datetime: datetime) -> int | None:
    prev_daily_question: QuerySet = find_dq_on_current_season(chat_id, target_datetime)
    if has_no(prev_daily_question):
        return None
    return prev_daily_question.get().question_author.id


def find_users_answer_on_dq(user_id: int, daily_question_id: int) -> QuerySet:
    users_answer: QuerySet = DailyQuestionAnswer.objects.filter(
        question=daily_question_id,
        answer_author=user_id
    )
    return users_answer


# ########################## Daily Question season ########################################
def save_dq_season(chat_id: int, start_datetime: datetime, season_number=1) -> int:
    chat = get_chat(chat_id)
    season = DailyQuestionSeason(chat=chat,
                                 season_number=season_number,
                                 start_datetime=start_datetime)
    season.save()
    return season.id


def get_dq_season(id: int) -> QuerySet:
    return DailyQuestionSeason.objects.get(id=id)


def find_dq_season(update: Update) -> QuerySet:
    date_of_question: datetime = update.message.date
    active_season_query: QuerySet = DailyQuestionSeason.objects.filter(
        chat=update.effective_chat.id,
        start_datetime__lte=date_of_question,
        end_datetime=None)
    return active_season_query


def find_dq_seasons_for_chat(chat_id: int) -> QuerySet:
    return DailyQuestionSeason.objects.filter(chat=chat_id).order_by('-start_datetime')


class SeasonNotFoundError(Exception):
    def __init__(self, update: Update):
        self.update = update


class DailyQuestionNotFoundError(Exception):
    def __init__(self, chat_id: int):
        self.chat_id = chat_id

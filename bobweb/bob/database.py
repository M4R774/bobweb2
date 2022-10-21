import os
import sys
from datetime import datetime, timedelta, date

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
def save_daily_question(update: Update, season: DailyQuestionSeason) -> DailyQuestion:
    question_author = get_telegram_user(update.effective_user.id)
    daily_question = DailyQuestion(season=season,
                                   datetime=update.message.date,
                                   message_id=update.effective_message.message_id,
                                   question_author=question_author,
                                   content=update.message.text)
    daily_question.save()
    return daily_question


def get_all_dq_on_season(season_id: int) -> QuerySet:
    return DailyQuestion.objects.filter(season=season_id).order_by('-id')


def find_all_dq_in_season(chat_id: int, target_datetime: datetime) -> QuerySet:
    return DailyQuestion.objects.filter(
        season__chat=chat_id,
        season__start_datetime__lte=target_datetime) \
        .filter(Q(season__end_datetime=None) | Q(season__end_datetime__gte=target_datetime)) \
        .order_by('-id')


def is_first_dq_in_season(update: Update) -> bool:
    return find_all_dq_in_season(update.effective_chat.id, update.message.date).count() == 0


def find_question_on_date(chat_id: int, target_datetime: datetime) -> QuerySet:
    return DailyQuestion.objects.filter(
        season__chat=chat_id,
        datetime__date=target_datetime.date())


def find_dq_by_message_id(message_id: int) -> QuerySet:
    return DailyQuestion.objects.filter(message_id=message_id)


def find_prev_daily_question_author_id(chat_id: int, target_datetime: datetime) -> int | None:
    prev_daily_question: QuerySet = find_all_dq_in_season(chat_id, target_datetime)
    if has_no(prev_daily_question):
        return None
    return prev_daily_question.get().question_author.id


def find_users_answer_on_dq(tg_user_id: int, daily_question_id: int) -> QuerySet:
    users_answer: QuerySet = DailyQuestionAnswer.objects.filter(
        question=daily_question_id,
        answer_author=tg_user_id
    ).order_by('-id')
    return users_answer


# ########################## Daily Question Answer ########################################
def save_or_update_dq_answer(update: Update, daily_question: DailyQuestion = None) -> DailyQuestionAnswer:
    if daily_question is None:
        daily_question = find_dq_by_message_id(update.message.reply_to_message.message_id).get()

    answer_author = get_telegram_user(update.effective_user.id)
    prev_answer = find_answer_by_user_to_dq(daily_question.id, answer_author.id)

    if has(prev_answer):
        return update_dq_answer(update, prev_answer.first())
    else:
        return save_dq_answer(update, daily_question, answer_author)


def update_dq_answer(update: Update, prev: DailyQuestionAnswer) -> DailyQuestionAnswer:
    # If user already has answered to the question, combine the answers
    new_content = f'{prev.content}\n\n' \
                  f'[{update.effective_message.date}] lisätty:' \
                  f'\n{update.effective_message.text}'
    prev.content = new_content
    prev.save()
    return prev


def save_dq_answer(update: Update, daily_question: DailyQuestion, author: TelegramUser) -> DailyQuestionAnswer:
    dq_answer = DailyQuestionAnswer(question=daily_question,
                                    datetime=update.effective_message.date,
                                    message_id=update.effective_message.message_id,
                                    answer_author=author,
                                    content=update.effective_message.text)
    dq_answer.save()
    return dq_answer


def find_answers_for_dq(dq_id: int) -> QuerySet:
    return DailyQuestionAnswer.objects.filter(question__id=dq_id).order_by('-id')


def find_answer_by_user_to_dq(dq_id: int, user_id: int) -> QuerySet:
    return DailyQuestionAnswer.objects.filter(question=dq_id, answer_author=user_id)


def find_answers_in_season(season_id: int) -> QuerySet:
    return DailyQuestionAnswer.objects.filter(question__season=season_id).order_by('-id')


# ########################## Daily Question season ########################################
def save_dq_season(chat_id: int, start_datetime: datetime, season_number=1) -> DailyQuestionSeason:
    chat = get_chat(chat_id)
    season = DailyQuestionSeason(chat=chat,
                                 season_number=season_number,
                                 start_datetime=start_datetime)
    season.save()
    return season


def get_dq_season(dq_season_id: int) -> QuerySet:
    return DailyQuestionSeason.objects.get(id=dq_season_id)


def find_dq_season(chat_id: int, target_datetime: datetime) -> QuerySet:
    return DailyQuestionSeason.objects.filter(
        chat=chat_id,
        start_datetime__lte=target_datetime,
        end_datetime=None)


def find_dq_seasons_for_chat(chat_id: int) -> QuerySet:
    return DailyQuestionSeason.objects.filter(chat=chat_id).order_by('-id')


class SeasonNotFoundError(Exception):
    def __init__(self, update: Update):
        self.update = update


class DailyQuestionNotFoundError(Exception):
    def __init__(self, chat_id: int):
        self.chat_id = chat_id

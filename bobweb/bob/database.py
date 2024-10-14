import os
import sys
from datetime import datetime, timezone
from typing import List

from django.db.models import QuerySet, Q, Count
from telegram import Update, Message

from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.utils_common import has, has_no, is_weekend, next_weekday, dt_at_midday, fitzstr_from
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
        bob = Bob(id=1, uptime_started_date=datetime.now(timezone.utc))
        bob.save()
        return bob


def get_global_admin():
    bob = get_the_bob()
    return bob.global_admin


def get_credit_card_holder():
    bob = get_the_bob()
    return bob.gpt_credit_card_holder


def set_credit_card_holder(new_credit_card_holder: TelegramUser):
    bob = get_the_bob()
    bob.gpt_credit_card_holder = new_credit_card_holder
    bob.save()


def get_gpt_system_prompt(chat_id: int) -> str:
    chat = Chat.objects.get(id=chat_id)
    return chat.gpt_system_prompt


def set_gpt_system_prompt(chat_id: int, new_system_prompt: str):
    chat = Chat.objects.get(id=chat_id)
    chat.gpt_system_prompt = new_system_prompt
    chat.save()


def get_quick_system_prompts(chat_id: int) -> dict:
    chat = Chat.objects.get(id=chat_id)
    return chat.quick_system_prompts


def set_quick_system_prompt(chat_id: int, new_quick_prompt_key: str, new_quick_prompt_value):
    chat = Chat.objects.get(id=chat_id)
    quick_system_prompts = chat.quick_system_prompts
    quick_system_prompts[new_quick_prompt_key] = new_quick_prompt_value
    chat.quick_system_prompts = quick_system_prompts
    chat.save()


def get_chats():
    return Chat.objects.all()


def get_chat(chat_id, title=None) -> Chat:
    if Chat.objects.filter(id=chat_id).count() <= 0:
        chat = Chat(id=chat_id)
        if int(chat_id) < 0:
            chat.title = title
        chat.save()
        return chat
    else:
        return Chat.objects.get(id=chat_id)


def get_chats_with_message_board() -> QuerySet:
    return Chat.objects.filter(message_board_msg_id__isnull=False)


def remove_message_board_from_chat(chat_id):
    chat = Chat.objects.get(id=chat_id)
    chat.message_board_msg_id = None
    chat.save()


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


def get_chat_members_for_chat(chat_id) -> QuerySet:
    return ChatMember.objects.filter(chat=chat_id)


def get_latest_weather_cities_for_members_of_chat(chat_id) -> List[str]:
    # Finds all non-null latest weather request _cities in chat and returns distinct list of those
    result: QuerySet = get_chat_members_for_chat(chat_id) \
            .filter(latest_weather_city__isnull=False) \
            .values_list('latest_weather_city', flat=True) \
            .distinct()
    return list(result)


def list_tg_users_for_chat(chat_id):
    # Find all TelegramUser's that have ChatMember with chat=chat_id
    return TelegramUser.objects.filter(id__in=ChatMember.objects.filter(chat=chat_id).values_list('tg_user', flat=True))


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


def update_user_in_db(update: Update):
    updated_user = get_telegram_user(update.effective_user.id)
    if update.effective_user.first_name is not None:
        updated_user.first_name = update.effective_user.first_name
    if update.effective_user.last_name is not None:
        updated_user.last_name = update.effective_user.last_name
    if update.effective_user.username is not None:
        updated_user.username = update.effective_user.username
    updated_user.save()

    if has_no(update.edited_message):  # No increment when message was editted by user
        increment_chat_member_message_count(update.effective_chat.id, update.effective_user.id)


# ########################## Daily Question ########################################
async def save_daily_question(update: Update, season: DailyQuestionSeason) -> DailyQuestion | None:
    chat_id = update.effective_chat.id
    dq_date = update.effective_message.date  # utc

    # date of question is either date of the update or next weekday (if question has already been asked or its weekend)
    dq_asked_today = find_question_on_date(chat_id, dq_date).first() is not None
    if is_weekend(dq_date) or dq_asked_today:
        date_of_question = dt_at_midday(next_weekday(dq_date))
    else:
        date_of_question = dt_at_midday(dq_date)

    # Prevent from saving more than 1 daily question per date. Note! date_of_question might be different from the date
    # that the question was sent
    dq_on_date_of_question = find_question_on_date(chat_id, date_of_question)
    if has(dq_on_date_of_question):
        await inform_date_of_question_already_has_question(update, date_of_question)
        return None

    question_author = get_telegram_user(update.effective_user.id)
    daily_question = DailyQuestion(season=season,
                                   created_at=update.effective_message.date,
                                   date_of_question=date_of_question,
                                   message_id=update.effective_message.message_id,
                                   question_author=question_author,
                                   content=update.effective_message.text)
    daily_question.save()
    return daily_question


async def inform_date_of_question_already_has_question(update: Update, date_of_question: datetime):
    reply_text = f'Kysymystä ei tallennettu. Syy:\nPäivämäärälle {fitzstr_from(date_of_question)} ' \
                 f'on jo tallennettu päivän kysymys.'
    await update.effective_chat.send_message(reply_text)


def get_all_dq_on_season(season_id: int) -> QuerySet:
    """
    Returns all but the first daily question of the season. Ordered by date of question asc.
    For example if there are daily questions for dates 01.01.2020, 02.01.2020, 03.01.2020,
    this returns [02.01.2020, 03.01.2020], and earliest question is found at index 0
    """
    return DailyQuestion.objects.filter(season=season_id).order_by('date_of_question')


def get_dq_count_on_season(season_id: int) -> int:
    """ Returns count of questions on a season """
    return DailyQuestion.objects.filter(season=season_id).count()


def find_all_dq_in_season(chat_id: int, target_datetime: datetime) -> QuerySet:
    return DailyQuestion.objects.filter(
        season__chat=chat_id,
        season__start_datetime__lte=target_datetime) \
        .filter(Q(season__end_datetime=None) | Q(season__end_datetime__gte=target_datetime)) \
        .order_by('-date_of_question')  # order by date of question descending


def is_first_dq_in_season(update: Update) -> bool:
    return find_all_dq_in_season(update.effective_chat.id, update.effective_message.date).count() == 1


def find_question_on_date(chat_id: int, target_datetime: datetime) -> QuerySet:
    return DailyQuestion.objects.filter(
        season__chat=chat_id,
        date_of_question__date=target_datetime.date())


def find_dq_by_message_id(message_id: int) -> QuerySet:
    return DailyQuestion.objects.filter(message_id=message_id)


def find_prev_daily_question(chat_id: int, target_datetime: datetime) -> DailyQuestion | None:
    return find_all_dq_in_season(chat_id, target_datetime).first()


def find_users_answer_on_dq(tg_user_id: int, daily_question_id: int) -> QuerySet:
    users_answer: QuerySet = DailyQuestionAnswer.objects.filter(
        question=daily_question_id,
        answer_author=tg_user_id
    ).order_by('id')  # Wanted in descending order so that .first() is always firs answer on dq
    return users_answer


# ########################## Daily Question Answer ########################################
def save_dq_answer(effective_message: Message,
                   daily_question: DailyQuestion,
                   author: TelegramUser) -> DailyQuestionAnswer:
    dq_answer = DailyQuestionAnswer(question=daily_question,
                                    created_at=effective_message.date,
                                    message_id=effective_message.message_id,
                                    answer_author=author,
                                    content=effective_message.text)
    dq_answer.save()
    return dq_answer


def save_dq_answer_without_message(daily_question: DailyQuestion,
                                   author_id: int,
                                   is_winning_answer=False) -> DailyQuestionAnswer:
    author = get_telegram_user(author_id)
    created_at = dt_at_midday(datetime.now(tz=fitz))
    dq_answer = DailyQuestionAnswer(question=daily_question,
                                    created_at=created_at,
                                    message_id=None,
                                    answer_author=author,
                                    content=None,
                                    is_winning_answer=is_winning_answer)
    dq_answer.save()
    return dq_answer


def find_answers_for_dq(dq_id: int) -> QuerySet:
    return DailyQuestionAnswer.objects.filter(question=dq_id).order_by('id')


def find_answer_by_user_to_dq(dq_id: int, user_id: int) -> QuerySet:
    return DailyQuestionAnswer.objects.filter(question=dq_id, answer_author=user_id)


def find_answers_in_season(season_id: int) -> QuerySet:
    return DailyQuestionAnswer.objects.filter(question__season=season_id).order_by('id')


def find_users_with_answers_in_season(season_id) -> List[TelegramUser]:
    # First find all users that have answered on at least one daily question on the season
    users_in_target_seasons_chat_sub = TelegramUser.objects \
        .annotate(answer_count=Count('daily_question_answer'))\
        .filter(chatmember__chat__daily_question_season__id=season_id, answer_count__gt=0) \
        .values('id')

    # Then count dq_count of all users in the previous subset
    result = TelegramUser.objects \
        .filter(Q(daily_question__season_id=season_id) | Q(daily_question__season_id__isnull=True)) \
        .filter(id__in=users_in_target_seasons_chat_sub) \
        .annotate(dq_count=Count('daily_question')) \
        .order_by('-dq_count')
    return list(result)


def find_answer_by_message_id(message_id: int) -> QuerySet:
    return DailyQuestionAnswer.objects.filter(message_id=message_id)


def find_next_dq_or_none(dq: DailyQuestion) -> DailyQuestion | None:
    try:
        return dq.get_next_by_date_of_question()
    except DailyQuestion.DoesNotExist:
        return None  # No next question


# ########################## Daily Question season ########################################
def save_dq_season(chat_id: int, start_datetime: datetime, season_name=1) -> DailyQuestionSeason:
    chat = get_chat(chat_id)
    season = DailyQuestionSeason(chat=chat,
                                 season_name=season_name,
                                 start_datetime=start_datetime)
    season.save()
    return season


def get_dq_season(dq_season_id: int) -> DailyQuestionSeason:
    return DailyQuestionSeason.objects.get(id=dq_season_id)


def get_seasons_for_chat(chat_id: int) -> List[DailyQuestionSeason]:
    return list(DailyQuestionSeason.objects.filter(chat=chat_id))


def find_latest_dq_season(chat_id: int, target_datetime: datetime) -> QuerySet:
    return DailyQuestionSeason.objects.filter(
        chat=chat_id,
        start_datetime__lte=target_datetime).order_by('-id')


def find_active_dq_season(chat_id: int, target_datetime: datetime) -> QuerySet:
    return find_latest_dq_season(chat_id, target_datetime).filter(end_datetime=None)


def find_dq_seasons_for_chat(chat_id: int) -> QuerySet:
    return DailyQuestionSeason.objects.filter(chat=chat_id).order_by('-id')


class SeasonListItem:
    def __init__(self, id: int, order_number: int, name: str):
        self.id: int = id
        self.order_number: int = order_number
        self.name: str = name


def find_dq_season_ids_for_chat(chat_id: int) -> List[SeasonListItem]:
    """ Returns dict of key: season_id, value: ordinal_order_of_season_in_chat """
    seasons = list(find_dq_seasons_for_chat(chat_id).order_by('id').values('id', 'season_name'))
    return [SeasonListItem(season['id'], i + 1, season['season_name']) for i, season in enumerate(seasons)]


class SeasonNotFoundError(Exception):
    def __init__(self, update: Update):
        self.update = update


class DailyQuestionNotFoundError(Exception):
    def __init__(self, chat_id: int):
        self.chat_id = chat_id

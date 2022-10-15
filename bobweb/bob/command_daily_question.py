from datetime import datetime
import string

from django.db.models import QuerySet
from telegram import Update, InlineKeyboardButton
from telegram.ext import CallbackContext

from bobweb.bob import command_service
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.daily_question.create_season_states import CreateSeasonActivity, SetSeasonStartDateState
from bobweb.bob.activities.daily_question.daily_question_menu_states import DQMainMenuState
from command import ChatCommand
from resources.bob_constants import PREFIXES_MATCHER, BOT_USERNAME
import database
from utils_common import has_one, has_no, has

#
# Daily Question -concept comprises two things:
#   - triggering an event when ever hashtag '#päivänkysymys' is used
#   - normal bob-commands for managing daily questions '/kysymys [command [parameters]]'
#


# Handles message that contains #päivänkysymys
# d = daily, q = question
class DailyQuestionHandler(ChatCommand):
    def __init__(self):
        super().__init__(
            name='#päivänkysymys',
            regex=r'(?i)#päivänkysymys',
            help_text_short=('#päivänkysymys', 'kyssäri')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_message_with_dq(update)

    def is_enabled_in(self, chat):
        return True


def handle_message_with_dq(update):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    dq_date = update.effective_message.date

    # dq_asked_today = database.get_question_on_date(chat_id, dq_date)
    # if has(dq_asked_today):
    #     return inform_q_already_asked(update)
    #
    # if is_weekend(dq_date):
    #     return inform_is_weekend(update)

    season = database.find_dq_season(update)
    if has_no(season):
        activity = CreateSeasonActivity(update_with_dq=update)
        initial_state = SetSeasonStartDateState(activity, update)
        activity.change_state(initial_state)
        command_service.instance.add_activity(activity)
        return  # Create season activity started and as such this daily question handling is halted

    # prev_dq_author_id = database.get_prev_daily_question_author_id(chat_id, dq_date)
    # if has(prev_dq_author_id) and prev_dq_author_id == user_id:
    #     return inform_author_is_same_as_previous_questions(update)

    # is weekday, season is active, no question yet asked => save new daily question
    database.save_daily_question(update, season.get())
    update.message.reply_text('tallennettu', quote=False)

    set_author_as_prev_dq_winner(update)


def inform_q_already_asked(update: Update):
    update.message.reply_text('päivänkysymys on jo kysytty', quote=False)


def inform_is_weekend(update: Update):
    update.message.reply_text('on viikonloppu', quote=False)


def is_weekend(target_datetime: datetime):
    # Monday == 1 ... Saturday == 6, Sunday == 7
    return target_datetime.isoweekday() >= 6


def inform_author_is_same_as_previous_questions(update: Update):
    update.message.reply_text('sama kysyjä kuin edellisessä. Ei tallennettu', quote=False)


def set_author_as_prev_dq_winner(update: Update):
    # If season has previous question without winner => make this updates sender it's winner
    prev_dq = database.find_dq_on_current_season(update.effective_chat.id, update.message.date)
    answers_to_dq = database.find_answers_for_dq(prev_dq.first().id)

    if has_no(prev_dq) and not database.is_first_dq_in_season(update):
        respond_with_winner_set_fail_msg(update, 'Edellistä tämän kauden kysymystä ei löytynyt.')
        return

    if has_no(answers_to_dq):
        respond_with_winner_set_fail_msg(update, 'Edellisen kysymykseen ei ole lainkaan vastauksia.')
        return

    if has_winner(answers_to_dq):
        respond_with_winner_set_fail_msg(update, 'Edellisen kysymyksen voittaja on jo merkattu.')
        return

    users_answer_to_prev_dq = database.find_users_answer_on_dq(update.effective_user.id, prev_dq.first().id).first()
    if has_one(users_answer_to_prev_dq):
        users_answer_to_prev_dq.is_winning_answer = True
        users_answer_to_prev_dq.save()
    else:
        respond_with_winner_set_fail_msg(update, 'Kysyjällä ei ole vastausta edelliseen kysymykseen.')


def has_winner(answers: QuerySet) -> bool:
    return has(answers) and len([a for a in answers if a.is_winning_answer]) > 0


def check_and_handle_reply_to_daily_question(update: Update):
    reply_target_dq = database.find_dq_by_message_id(update.message.reply_to_message.message_id)
    if has_no(reply_target_dq):
        return  # Was not replying to dailyQuestion -> nothign happens

    database.save_or_update_dq_answer(update, reply_target_dq.get())


def respond_with_winner_set_fail_msg(update: Update, reason: string):
    message_text = f'Virhe edellisen kysymyksen voittajan tallentamisessa.\nSyy: {reason}'
    update.message.reply_text(message_text, quote=False, parse_mode='Markdown')


# ####################### DAILY QUESTION COMMANDS ######################################


# Manages normal commands related to daily questions
class DailyQuestionCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='kysymys cli',
            regex=f'(?i)^{PREFIXES_MATCHER}kysymys($|\s)',  # Either message with hashtag or command
            help_text_short=('/kysymys', 'kyssärikomento')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.handle_kysymys_command(update)

    def is_enabled_in(self, chat):
        return True

    def handle_kysymys_command(self, update):
        fist_state = DQMainMenuState(initial_update=update)
        activity = CommandActivity()
        activity.change_state(fist_state)
        command_service.instance.add_activity(activity)

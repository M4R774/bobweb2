from datetime import datetime, date
import string
from enum import Enum

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob import command_service
from bobweb.bob.activities.daily_question_activities import CreateSeasonActivity, SetSeasonStartDateState
from command import ChatCommand
from resources.bob_constants import PREFIXES_MATCHER, BOT_USERNAME
import database
from utils_common import has, has_one, has_no

#
# Daily Question -concept comprises two things:
#   - triggering an event when ever hashtag '#päivänkysymys' is used
#   - normal bob-commands for managing daily questions '/kysymys [command [parameters]]'
#

# in memory storage for updates that contain daily_question that cannot be saved to database yet
daily_question_update_storage = []


# Handles message that contains #päivänkysymys
# d = daily, q = question
class DailyQuestion(ChatCommand):
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
    dq_date = update.message.date

    # dq_asked_today = database.get_question_on_date(chat_id, dq_date)
    # if has(dq_asked_today):
    #     return inform_q_already_asked(update)
    #
    # if is_weekend(dq_date):
    #     return inform_is_weekend(update)

    season = database.find_dq_season(update)
    # if has_no(season):
    if True:
        # Pitää löytää botin activity
        activity = CreateSeasonActivity(update_with_dq=update)
        initial_state = SetSeasonStartDateState(activity, update)
        activity.change_state(initial_state)
        command_service.command_service_instance.add_activity(activity)
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
    tg_user = database.get_telegram_user(update.effective_user.id)
    prev_dq_without_winner = database.find_dq_on_current_season(update.effective_chat.id, update.message.date)

    if has_no(prev_dq_without_winner) and not database.is_first_dq_in_season(update):
        respond_with_winner_set_fail_msg(update, 'Edellistä tämän kauden kysymystä ei löytynyt.')
        return

    # elif prev_dq_without_winner.count() > 0:
    #     respond_with_winner_set_fail_msg(update, 'Edellisiä kysymyksiä ilmaan voittajamerkintää löytyi liian monta.')
    # elif prev_dq_without_winner.get().winner_user is not None:
    #     respond_with_winner_set_fail_msg(update, 'Edellisen kysymyksen voittaja on jo merkattu.')

    users_answer_to_prev_dq = database.find_users_answer_on_dq(tg_user.id, prev_dq_without_winner.first().id)

    if has_one(users_answer_to_prev_dq):
        users_answer_to_prev_dq.get().is_winning_answer = True
        users_answer_to_prev_dq.get().save()
    else:
        respond_with_winner_set_fail_msg(update, 'Kysyjällä ei ole vastausta edelliseen kysymykseen.')


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
        update.message.reply_text('/kysymys', quote=False)


def get_go_to_private_chat_button():
    keyboard = [
        [InlineKeyboardButton(text='Jatketaan yksityisviesteillä',
                              url=f'https://t.me/{BOT_USERNAME}?start=start',
                              callback_data='create_season')],
        [InlineKeyboardButton(text='callback testi',
                              callback_data='create_season')],
    ]
    return keyboard


def go_back_button():
    return [InlineKeyboardButton(text='<-',
                                 callback_data='go_back')]


def respond_with_winner_set_fail_msg(update: Update, reason: string):
    message_text = f'Virhe edellisen kysymyksen voittajan tallentamisessa.\nSyy: {reason}'
    update.message.reply_text(message_text, quote=False, parse_mode='Markdown')

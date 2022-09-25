import datetime
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

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
class DailyQuestion(ChatCommand):
    def __init__(self):
        super().__init__(
            name='#päivänkysymys',
            regex=r'(?i)#päivänkysymys',
            help_text_short=('#päivänkysymys', 'kyssäri')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_message_with_kysymys(update)

    def is_enabled_in(self, chat):
        return True


def handle_message_with_kysymys(update):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    dq_date = update.message.date

    todays_question = database.get_todays_question(update)
    if has(todays_question):
        return inform_question_already_asked(update)

    if is_weekend():
        return inform_is_weekend(update)

    season = database.get_daily_question_season(update)
    if has_no(season):
        return start_create_season_activity(update)

    prev_dq_author_id = database.get_prev_daily_question_author_id(chat_id, dq_date)
    if has(prev_dq_author_id) and prev_dq_author_id == user_id:
        return inform_author_is_same_as_previous_questions(update)

    # is weekday, season is active, no question yet asked => save new daily question
    database.save_daily_question(update, season.get())
    update.message.reply_text('tallennettu', quote=False)

    set_previous_question_winner_if_conditions_met(update)


def inform_question_already_asked(update: Update):
    update.message.reply_text('päivänkysymys on jo kysytty', quote=False)


def inform_is_weekend(update: Update):
    update.message.reply_text('on viikonloppu', quote=False)


def is_weekend():
    # Monday == 1 ... Saturday == 6, Sunday == 7
    return datetime.date.today().isoweekday() >= 6


def inform_author_is_same_as_previous_questions(update: Update):
    update.message.reply_text('sama kysyjä kuin edellisessä. Ei tallennettu', quote=False)


def set_previous_question_winner_if_conditions_met(update: Update):
    # If season has previous question without winner => make this updates sender it's winner
    prev_dq = database.get_prev_daily_question_on_current_season(update.effective_chat.id, update.message.date)
    tg_user = database.get_telegram_user(update.effective_user.id)

    if prev_dq is not None and prev_dq.winner_user is None:
        prev_dq.winner_user = tg_user
        prev_dq.save()


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


def start_create_season_activity(update: Update) -> None:
    daily_question_update_storage.append(update)
    markup = InlineKeyboardMarkup(get_go_to_private_chat_button())
    update.message.reply_text('Ei aktiivista kysymyskautta. Anna kauden numero:',
                              reply_markup=markup)
    database.save_daily_question_season(update, update.message.date)


def get_go_to_private_chat_button():
    keyboard = [
        [InlineKeyboardButton(text='Jatketaan yksityisviesteillä',
                              url=f'https://t.me/{BOT_USERNAME}?start=start',
                              callback_data='create_season')],
        [InlineKeyboardButton(text='callback testi',
                              callback_data='create_season')],
    ]
    return keyboard

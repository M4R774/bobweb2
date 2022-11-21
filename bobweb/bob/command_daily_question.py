from datetime import datetime, timedelta
import string

from django.db.models import QuerySet
from telegram import Update, InlineKeyboardButton
from telegram.ext import CallbackContext

from bobweb.bob import command_service
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.daily_question.start_season_states import StartSeasonActivity, SetSeasonStartDateState
from bobweb.bob.activities.daily_question.daily_question_menu_states import DQMainMenuState
from bobweb.web.bobapp.models import DailyQuestion, DailyQuestionAnswer
from bobweb.bob.command import ChatCommand
from bobweb.bob.resources.bob_constants import PREFIXES_MATCHER
from bobweb.bob import database
from bobweb.bob.utils_common import has_one, has_no, has, auto_remove_msg_after_delay


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

    invoke_on_edit = True  # Should be invoked on message edits
    invoke_on_reply = True  # Should be invoked on message replies

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_message_with_dq(update, context)


def handle_message_with_dq(update, context):
    created_from_edited_message = False

    if has(update.edited_message):
        # Search possible previous daily question by message id. If has update it's content
        dq_today: DailyQuestion = database.find_dq_by_message_id(update.edited_message.message_id).first()
        if has(dq_today):
            dq_today.content = update.edited_message.text
            dq_today.save()
            return
        created_from_edited_message = True
        # if is edit, but no question is yet persisted => continue normal process

    chat_id = update.effective_chat.id
    dq_date = update.effective_message.date
    season = database.find_active_dq_season(chat_id, dq_date.date())
    if has_no(season):
        activity = StartSeasonActivity(state=SetSeasonStartDateState(), update_with_dq=update)
        command_service.instance.add_activity(activity)
        return  # Create season activity started and as such this daily question handling is halted

    user_id = update.effective_user.id
    prev_dq_author_id = database.find_prev_daily_question_author_id(chat_id, dq_date)
    if has(prev_dq_author_id) and prev_dq_author_id == user_id:
        # NOTE!!! DISABLE FOR EASY LOCAL DEVELOPMENT AND TESTING #
        return inform_author_is_same_as_previous_questions(update)

    saved_dq = database.save_daily_question(update, season.get())
    if has_no(saved_dq):
        return  # No question was saved

    if created_from_edited_message:
        inform_dq_created_from_message_edit(update)
        notification_text = None  # Information given as a staying message, so no notification
    else:
        notification_text = 'Kysymys tallennettu'

    if has(saved_dq):  # If DailyQuestion save was successful
        winner_set = set_author_as_prev_dq_winner(update)
        if winner_set:
            notification_text = 'Kysymys ja edellisen kysymyksen voittaminen tallennettu'

    # Notification that is removed automatically
    if has(notification_text):
        reply = update.effective_message.reply_text(notification_text, quote=False)
        auto_remove_msg_after_delay(reply, context)

def inform_author_is_same_as_previous_questions(update: Update):
    reply_text = 'Päivän kysyjä on sama kuin aktiivisen kauden edellisessä kysymyksessä. Kysymystä ei tallennetu.'
    update.effective_message.reply_text(reply_text, quote=False)


def inform_dq_created_from_message_edit(update: Update):
    message_text = 'Päivän kysymys tallennettu jälkikäteen lisätyn \'#päivänkysymys\' tägin myötä. Muokkausta ' \
                   'edeltäviä vastauksia ei ole tallennettu vastauksiksi'
    update.effective_message.reply_text(message_text, quote=False)


def set_author_as_prev_dq_winner(update: Update) -> True:
    # If season has previous question without winner => make this updates sender it's winner
    prev_dq: DailyQuestion = database.find_all_dq_in_season(update.effective_chat.id, update.effective_message.date)\
        .filter(created_at__lt=update.effective_message.date).first()  # only dq that has been saved before now given dq

    if has_no(prev_dq):
        return False  # Is first question in a season. No prev question to mark as winner

    answers_to_dq = database.find_answers_for_dq(prev_dq.id)

    if has(prev_dq) and has_no(answers_to_dq):
        respond_with_winner_set_fail_msg(update, 'Edelliseen kysymykseen ei ole lainkaan vastauksia.')
        return False

    if has_winner(answers_to_dq):
        respond_with_winner_set_fail_msg(update, 'Edellisen kysymyksen voittaja on jo merkattu.')
        return False

    users_answer_to_prev_dq = answers_to_dq.filter(answer_author=update.effective_user.id).first()
    if has_one(users_answer_to_prev_dq):
        users_answer_to_prev_dq.is_winning_answer = True
        users_answer_to_prev_dq.save()
        return True
    else:
        respond_with_winner_set_fail_msg(update, 'Kysyjällä ei ole vastausta edelliseen kysymykseen.')
        return False


def has_winner(answers: QuerySet) -> bool:
    return has(answers) and len([a for a in answers if a.is_winning_answer]) > 0


def check_and_handle_reply_to_daily_question(update: Update, context: CallbackContext):
    reply_target_dq = database.find_dq_by_message_id(
        update.effective_message.reply_to_message.message_id).first()
    if has_no(reply_target_dq):
        return  # Was not replying to dailyQuestion -> nothing happens

    answer_author = database.get_telegram_user(update.effective_user.id)

    if has(update.edited_message):
        target_dq_answer: DailyQuestionAnswer = database.find_answer_by_message_id(
            update.edited_message.message_id).first()
        target_dq_answer.content = update.edited_message.text
        target_dq_answer.save()
    else:
        database.save_dq_answer(update.effective_message, reply_target_dq, answer_author)
    reply = update.effective_message.reply_text('Vastaus tallennettu', quote=False)
    auto_remove_msg_after_delay(reply, context)


def respond_with_winner_set_fail_msg(update: Update, reason: string):
    message_text = f'Virhe edellisen kysymyksen voittajan tallentamisessa.\nSyy: {reason}'
    update.effective_message.reply_text(message_text, quote=False, parse_mode='Markdown')


# ####################### DAILY QUESTION COMMANDS ######################################


# Manages normal commands related to daily questions
class DailyQuestionCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='kysymys',
            regex=f'(?i)^{PREFIXES_MATCHER}kysymys($|\s)',
            help_text_short=('/kysymys', 'kyssärikomento')
        )
    invoke_on_edit = True  # Should be invoked on message edits

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_kysymys_command(update)


def handle_kysymys_command(update):
    first_state = DQMainMenuState(initial_update=update)
    activity = CommandActivity(state=first_state)
    command_service.instance.add_activity(activity)


# Manages situations, where answer to daily question has not been registered or saved
# 1. - DailyQuestion is given and saved
#    - User has answered without replying to the question message
#    - Any user replies to the answer message with message that contains '/vastaus'
# => this command is triggered, and the message that was edited or that was replied to is saved as an answer
class MarkAnswerCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='vastaus',
            regex=f'(?i)^{PREFIXES_MATCHER}vastaus$',
            help_text_short=('/vastaus', 'merkkaa vastauksen')
        )
    invoke_on_edit = True  # Should be invoked on message edits
    invoke_on_reply = True  # Should be invoked on message replies

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_mark_message_as_answer_command(update)


def handle_mark_message_as_answer_command(update):
    message_with_answer = update.effective_message.reply_to_message
    # Check that message_with_answer has not yet been saved as an answer
    answer_from_database = database.find_answer_by_message_id(message_with_answer.message_id)
    if has(answer_from_database):
        update.effective_message.reply_text('Kohdeviesti on jo tallennettu aiemmin.')
        return  # Target message has already been saved as an answer to a question

    prev_dq = database.find_all_dq_in_season(update.effective_chat.id, message_with_answer.date).first()
    answer_author = database.get_telegram_user(message_with_answer.from_user.id)
    database.save_dq_answer(message_with_answer, prev_dq, answer_author)
    update.effective_message.reply_text('Kohdeviesti tallennettu onnistuneesti vastauksena kysymykseen!')


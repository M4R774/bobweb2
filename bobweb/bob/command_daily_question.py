import string

from django.db.models import QuerySet
from telegram import Update, Message
from telegram.ext import CallbackContext

from bobweb.bob import command_service
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.daily_question.add_missing_answer_state import MarkAnswerOrSaveAnswerWithoutMessage
from bobweb.bob.activities.daily_question.daily_question_errors import LastQuestionWinnerAlreadySet, \
    NoAnswerFoundToPrevQuestion
from bobweb.bob.activities.daily_question.date_confirmation_states import ConfirmQuestionTargetDate
from bobweb.bob.activities.daily_question.message_utils import get_daily_question_notification
from bobweb.bob.activities.daily_question.start_season_states import SetSeasonStartDateState
from bobweb.bob.activities.daily_question.daily_question_menu_states import DQMainMenuState
from bobweb.web.bobapp.models import DailyQuestion, DailyQuestionAnswer
from bobweb.bob.command import ChatCommand, regex_simple_command
from bobweb.bob import database
from bobweb.bob.utils_common import has_one, has_no, has, auto_remove_msg_after_delay, weekday_count_between


# Handles message that contains #päivänkysymys
# d = daily, q = question
class DailyQuestionHandler(ChatCommand):
    def __init__(self):
        super().__init__(
            name='#päivänkysymys',
            regex=r'(?i)#päivänkysymys',  # case-insensitive and detected from anywhere in the message
            help_text_short=('#päivänkysymys', 'kyssäri')
        )

    invoke_on_edit = True  # Should be invoked on message edits
    invoke_on_reply = True  # Should be invoked on message replies

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_message_with_dq(update, context)


def handle_message_with_dq(update: Update, context: CallbackContext):
    if has(update.edited_message):
        # Search possible previous daily question by message id. If has update it's content
        dq_today: DailyQuestion = database.find_dq_by_message_id(update.edited_message.message_id).first()
        if has(dq_today):
            dq_today.content = update.edited_message.text
            dq_today.save()
            return  # Update already persisted daily question content without creating a new one
        # if is edit, but no question is yet persisted => continue normal process

    chat_id = update.effective_chat.id
    dq_date = update.effective_message.date  # utc
    season = database.find_active_dq_season(chat_id, dq_date)
    if has_no(season):
        activity = CommandActivity(initial_update=update, state=SetSeasonStartDateState())
        command_service.instance.add_activity(activity)
        return  # Create season activity started and as such this daily question handling is halted

    # Check that update author is not same as prev dq author. If so, inform
    prev_dq = database.find_prev_daily_question(chat_id, dq_date)
    if has(prev_dq) and prev_dq.question_author.id == update.effective_user.id:
        if prev_dq.created_at.date() == dq_date.date() or prev_dq.date_of_question == dq_date.date():
            # Let's assume here that user has used the hashtag '#päivänkysymys' again in his right answer message
            # and as such is not trying to create a new daily question
            return
        else:
            return inform_author_is_same_as_previous_questions(update)

    saved_dq = database.save_daily_question(update, season.get())
    if has_no(saved_dq):
        return  # No question was saved

    notification_text = None
    winner_set = False
    try:
        winner_set = set_author_as_prev_dq_winner(update, prev_dq)
    except LastQuestionWinnerAlreadySet as e:
        notification_text = e.localized_msg
    except NoAnswerFoundToPrevQuestion:
        # Starts new activity that contains instructions how to handle this error
        state = MarkAnswerOrSaveAnswerWithoutMessage(prev_dq=prev_dq, answer_author_id=update.effective_user.id)
        command_service.instance.add_activity(CommandActivity(initial_update=update, state=state))
        return  # MarkAnswerOrSaveAnswerWithoutMessage takes care of the rest

    # If there is gap in weekdays between this and last question ask user which dates question this is
    if has(prev_dq) and weekday_count_between(prev_dq.date_of_question, dq_date) > 1:
        state = ConfirmQuestionTargetDate(prev_dq=prev_dq, current_dq=saved_dq, winner_set=winner_set)
        command_service.instance.add_activity(CommandActivity(initial_update=update, state=state))
        return  # ConfirmQuestionTargetDate takes care of rest

    if notification_text is None:
        notification_text = get_daily_question_notification(update, winner_set)

    notification_message = update.effective_chat.send_message(notification_text)

    # If everything goes as expected, dq saved notification message is removed after delay
    if winner_set and has_no(update.edited_message):
        auto_remove_msg_after_delay(notification_message, context)


def inform_author_is_same_as_previous_questions(update: Update):
    reply_text = 'Päivän kysyjä on sama kuin aktiivisen kauden edellisessä kysymyksessä. Kysymystä ei tallennetu.'
    update.effective_chat.send_message(reply_text)


def set_author_as_prev_dq_winner(update: Update, prev_dq: DailyQuestion) -> bool:
    """
    Sets authors reply to previous question as a winning one. If author had no answer or answer has already
        been set, raises appropriate error.
    :param update: Telegram Update
    :param prev_dq: previous DailyQuestion
    :return: bool - True if winner_set
    """
    if has_no(prev_dq):
        return False  # Is first question in a season. No prev question to mark as winner so not an error

    answers_to_dq = database.find_answers_for_dq(prev_dq.id)

    if has_winner(answers_to_dq):  # would only happen in case of a bug
        raise LastQuestionWinnerAlreadySet()

    users_answer_to_prev_dq = answers_to_dq.filter(answer_author=update.effective_user.id).first()
    if has(users_answer_to_prev_dq):
        users_answer_to_prev_dq.is_winning_answer = True
        users_answer_to_prev_dq.save()
        return True
    else:  # quite probable
        raise NoAnswerFoundToPrevQuestion()


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


# ####################### DAILY QUESTION COMMANDS ######################################


# Manages normal commands related to daily questions
class DailyQuestionCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='kysymys',
            regex=regex_simple_command('kysymys'),
            help_text_short=('/kysymys', 'kyssärikomento')
        )

    invoke_on_edit = True  # Should be invoked on message edits

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_kysymys_command(update)


def handle_kysymys_command(update):
    activity = CommandActivity(initial_update=update, state=DQMainMenuState())
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
            regex=regex_simple_command('vastaus'),
            help_text_short=('/vastaus', 'merkkaa vastauksen')
        )

    invoke_on_edit = True  # Should be invoked on message edits
    invoke_on_reply = True  # Should be invoked on message replies

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_mark_message_as_answer_command(update)


def handle_mark_message_as_answer_command(update):
    message_with_answer = update.effective_message.reply_to_message
    if has_no(message_with_answer):
        update.effective_message.reply_text('Ei kohdeviestiä, mitä merkata vastaukseksi. Käytä Telegramin \'reply\''
                                            '-toimintoa merkataksesi tällä komennolla toisen viestin vastaukseksi')
        return  # No target message to save as answer

    # Check that message_with_answer has not yet been saved as an answer
    answer_from_database = database.find_answer_by_message_id(message_with_answer.message_id)
    if has(answer_from_database):
        update.effective_message.reply_text('Kohdeviesti on jo tallennettu aiemmin vastaukseksi.')
        return  # Target message has already been saved as an answer to a question

    dq_on_target_date = DailyQuestion.objects.filter(created_at__lt=message_with_answer.date,
                                                     season__chat__id=message_with_answer.chat.id).first()
    answer_author = database.get_telegram_user(message_with_answer.from_user.id)
    answer = database.save_dq_answer(message_with_answer, dq_on_target_date, answer_author)
    reply_msg = target_msg_saved_as_answer_msg

    # IF    - dq on target date has no winning answer set yet,
    #   AND - message_with_answer author has sent the next daily question
    # THEN  - set saved answer to be the winning one and set response to reflect that

    no_winning_answer = database.find_answers_for_dq(dq_on_target_date.id).filter(is_winning_answer=True).count() == 0
    next_dq = database.find_next_dq_or_none(dq_on_target_date)

    if no_winning_answer and has(next_dq) and next_dq.question_author.id == answer_author.id:
        answer.is_winning_answer = True
        answer.save()
        reply_msg = target_msg_saved_as_winning_answer_msg

    update.effective_message.reply_text(reply_msg)


target_msg_saved_as_answer_msg = 'Kohdeviesti tallennettu onnistuneesti vastauksena kysymykseen!'
target_msg_saved_as_winning_answer_msg = 'Kohdeviesti tallennettu onnistuneesti voittaneena vastauksena sitä ' \
                                         'edeltäneeseen päivän kysymykseen'

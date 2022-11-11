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
from bobweb.bob.utils_common import has_one, has_no, has

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

    def handle_update(self, update: Update, context: CallbackContext = None):
        handle_message_with_dq(update)


def handle_message_with_dq(update):
    # chat_id = update.effective_chat.id
    # user_id = update.effective_user.id
    # dq_date = update.effective_message.date
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

        # Tähän huomautus käyttäjälle (jos kysymys lisätään) että editointia edeltäviä vastauksia ei ole
        # pystytty tallentamaan

    season = database.find_dq_season(update.effective_chat.id, update.effective_message.date.date())
    if has_no(season):
        activity = StartSeasonActivity(update_with_dq=update)
        initial_state = SetSeasonStartDateState(activity)
        activity.change_state(initial_state)
        command_service.instance.add_activity(activity)
        return  # Create season activity started and as such this daily question handling is halted

    ########### Kommentoitu vain kehityksen ajaksi pois
    # prev_dq_author_id = database.get_prev_daily_question_author_id(chat_id, dq_date)
    # if has(prev_dq_author_id) and prev_dq_author_id == user_id:
    #     return inform_author_is_same_as_previous_questions(update)

    saved_dq = database.save_daily_question(update, season.get())

    if created_from_edited_message:
        inform_dq_created_from_message_edit(update)
    else:
        update.effective_message.reply_text('tallennettu', quote=False)

    if has(saved_dq):  # If DailyQuestion save was successful
        set_author_as_prev_dq_winner(update)


def inform_author_is_same_as_previous_questions(update: Update):
    update.effective_message.reply_text('sama kysyjä kuin edellisessä. Ei tallennettu', quote=False)


def inform_dq_created_from_message_edit(update: Update):
    message_text = 'Päivän kysymys tallennettu jälkikäteen lisätyn \'#päivänkysymys\' tägin myötä. Muokkausta ' \
                   'edeltäviä vastauksia ei ole tallennettu vastauksiksi'
    # todo: tapa merkitä ennen kysymyksen muokkausta annetut vastaukset vastauksiksi
    update.effective_message.reply_text(message_text, quote=False)


def set_author_as_prev_dq_winner(update: Update):
    # If season has previous question without winner => make this updates sender it's winner
    prev_dq: DailyQuestion = database.find_all_dq_in_season(update.effective_chat.id, update.effective_message.date)\
        .filter(datetime__lt=update.effective_message.date).first()  # only dq that has been saved before now given dq
    answers_to_dq = database.find_answers_for_dq(prev_dq.id)

    if has_no(prev_dq) and not database.is_first_dq_in_season(update):
        respond_with_winner_set_fail_msg(update, 'Edellistä tämän kauden kysymystä ei löytynyt.')
        return

    if has(prev_dq) and has_no(answers_to_dq):
        respond_with_winner_set_fail_msg(update, 'Edellisen kysymykseen ei ole lainkaan vastauksia.')
        return

    if has_winner(answers_to_dq):
        respond_with_winner_set_fail_msg(update, 'Edellisen kysymyksen voittaja on jo merkattu.')
        return

    users_answer_to_prev_dq = answers_to_dq.filter(answer_author=update.effective_user.id).first()
    if has_one(users_answer_to_prev_dq):
        users_answer_to_prev_dq.is_winning_answer = True
        users_answer_to_prev_dq.save()
    else:
        respond_with_winner_set_fail_msg(update, 'Kysyjällä ei ole vastausta edelliseen kysymykseen.')


def has_winner(answers: QuerySet) -> bool:
    return has(answers) and len([a for a in answers if a.is_winning_answer]) > 0


def check_and_handle_reply_to_daily_question(update: Update):
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
        database.save_dq_answer(update, reply_target_dq, answer_author)


def respond_with_winner_set_fail_msg(update: Update, reason: string):
    message_text = f'Virhe edellisen kysymyksen voittajan tallentamisessa.\nSyy: {reason}'
    update.effective_message.reply_text(message_text, quote=False, parse_mode='Markdown')


# ####################### DAILY QUESTION COMMANDS ######################################


# Manages normal commands related to daily questions
class DailyQuestionCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='kysymys',
            regex=f'(?i)^{PREFIXES_MATCHER}kysymys($|\s)',  # Either message with hashtag or command
            help_text_short=('/kysymys', 'kyssärikomento')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        self.handle_kysymys_command(update)

    def handle_kysymys_command(self, update):
        fist_state = DQMainMenuState(initial_update=update)
        activity = CommandActivity()
        activity.change_state(fist_state)
        command_service.instance.add_activity(activity)

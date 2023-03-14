from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.utils_common import has
from bobweb.web.bobapp.models import DailyQuestion, TelegramUser


class MarkAnswerOrSaveAnswerWithoutMessage(ActivityState):
    def __init__(self, prev_dq: DailyQuestion, answer_author: TelegramUser):
        super().__init__()
        self.prev_dq = prev_dq
        self.answer_author = answer_author

    def execute_state(self):
        markup = InlineKeyboardMarkup([[new_answer_btn]])
        self.activity.reply_or_update_host_message(message_saved_no_answer_to_last_dq, markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == new_answer_btn.callback_data:
            self.save_new_winning_answer()

    def save_new_winning_answer(self):
        answer = database.save_dq_answer_without_message(daily_question=self.prev_dq,
                                                         author=self.answer_author,
                                                         is_winning_answer=True)
        if has(answer.id):
            self.activity.reply_or_update_host_message(text=answer_without_message_saved,
                                                       markup=InlineKeyboardMarkup([[]]))
            self.activity.done()


message_saved_no_answer_to_last_dq = 'Kysymys tallennettu. Ei vastausta edelliseen kysymykseen jota merkata ' \
                                     'voittaneeksi. Jos olet vastannut tässä merkkaa vastausviestisi vastaamalla ' \
                                     '(reply) siihen viestillä \'/vastaus\'. Jos vastaus on on annettu muuten, ' \
                                     'voit lisätä viestittömän voittaneen vastauksen alta'

new_answer_btn = InlineKeyboardButton(text='Viestitön voittanut vastaus', callback_data='/new_answer')
answer_without_message_saved = 'Uusi viestitön voittanut vastaus tallennettu!'

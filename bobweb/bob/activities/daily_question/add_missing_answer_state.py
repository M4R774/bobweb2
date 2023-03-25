from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.utils_common import has
from bobweb.web.bobapp.models import DailyQuestion, TelegramUser


class MarkAnswerOrSaveAnswerWithoutMessage(ActivityState):
    def __init__(self, prev_dq: DailyQuestion, answer_author_id: int):
        super().__init__()
        self.prev_dq = prev_dq
        self.answer_author_id = answer_author_id

    def execute_state(self):
        markup = InlineKeyboardMarkup([[new_answer_btn]])
        self.activity.reply_or_update_host_message(message_saved_no_answer_to_last_dq, markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == new_answer_btn.callback_data:
            self.try_to_save_new_answer()

    def try_to_save_new_answer(self):
        # As user could have marked their previous message as an answer, it is checked again that the target dq
        # does not yet have winning answer
        no_winning_answer = database.find_answers_for_dq(self.prev_dq.id).filter(is_winning_answer=True).count() == 0
        if no_winning_answer:
            self.save_new_answer()
        else:
            self.activity.reply_or_update_host_message(text=daily_question_already_has_winning_answer,
                                                       markup=InlineKeyboardMarkup([[]]))
            self.activity.done()


    def save_new_answer(self):
        answer = database.save_dq_answer_without_message(daily_question=self.prev_dq,
                                                         author_id=self.answer_author_id,
                                                         is_winning_answer=True)
        if has(answer.id):
            self.activity.reply_or_update_host_message(text=answer_without_message_saved,
                                                       markup=InlineKeyboardMarkup([[]]))
            self.activity.done()


message_saved_no_answer_to_last_dq = 'Kysymys tallennettu. Ei vastausta edelliseen kysymykseen jota merkata ' \
                                     'voittaneeksi. Jos olet vastannut tässä ryhmässä merkitse vastausviestisi ' \
                                     'vastaamalla (reply) siihen komennolla \'/vastaus\'. Voit vaihtoehtoisesti myös' \
                                     'lisätä viestittömän voittaneen vastauksen alta'

new_answer_btn = InlineKeyboardButton(text='Lisää viestitön voittanut vastaus', callback_data='/new_answer')
answer_without_message_saved = 'Uusi viestitön voittanut vastaus tallennettu!'

daily_question_already_has_winning_answer = 'Päivän kysymys on saanut välissä voittaneen vastauksen. Uutta viestitöntä ' \
                                            'voittanutta vastausta ei tallennetu.'

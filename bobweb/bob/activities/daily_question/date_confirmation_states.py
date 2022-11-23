from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import parse_date, date_invalid_format_text
from bobweb.bob.activities.daily_question.message_utils import dq_saved_msg
from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT
from bobweb.bob.utils_common import prev_weekday, has_no, start_of_date, d_fi_name, d_fi
from bobweb.web.bobapp.models import DailyQuestion


class ConfirmQuestionTargetDate(ActivityState):
    def __init__(self, prev_dq: DailyQuestion, current_dq: DailyQuestion, winner_set: bool):
        super().__init__()
        self.prev_dq = prev_dq
        self.current_dq = current_dq  # If of the daily question which date of question is being confirmed
        self.winner_set = winner_set
        self.reply_text = f'{dq_saved_msg(self.winner_set)}. Kysymysjatkumossa on kuitenkin aukko, joten vahvistatko ' \
                          f'vielä minkä päivän päivän kysymys on kyseessä valitsemalla alapuolelta tai vastaamalla ' \
                          f'päivämäärällä.'

    def execute_state(self):
        markup = InlineKeyboardMarkup(day_buttons())
        self.activity.reply_or_update_host_message(self.reply_text, markup)

    def preprocess_reply_data(self, text: str) -> str | None:
        date = parse_date(text)
        if has_no(date):
            reply_text = f'{self.reply_text}\n\n{date_invalid_format_text}'
            self.activity.reply_or_update_host_message(reply_text)
        return date

    def handle_response(self, response_data: str, context: CallbackContext = None):
        date_obj = start_of_date(datetime.fromisoformat(response_data))
        prev_dq_date_str = self.prev_dq.date_of_question.strftime(FINNISH_DATE_FORMAT)
        if date_obj.date() <= self.prev_dq.date_of_question.date():
            reply_text = f'{self.reply_text}\n\nPäivämäärä voi olla aikaisintaan edellistä kysymystä seuraava päivä. ' \
                         f'Edellisen kysymyksen päivä on {prev_dq_date_str}.'
            self.activity.reply_or_update_host_message(reply_text)
            return  # given date was not valid

        # Inform user that the date has been confirmed and
        is_today = date_obj.date() == self.current_dq.date_of_question.date()
        date_of_q_str = 'tämä päivä' if is_today else date_obj.strftime(FINNISH_DATE_FORMAT)
        winner_set_str = f' ja kysyjä merkitty voittajaksi päivän {prev_dq_date_str} kysymykseen.'
        reply_text = f'{dq_saved_msg(self.winner_set)} Kysymyksen päiväksi vahvistettu {date_of_q_str}' \
                     f'{winner_set_str if self.winner_set else "."}'

        self.current_dq.date_of_question = date_obj
        self.current_dq.save()
        self.activity.reply_or_update_host_message(reply_text, InlineKeyboardMarkup([]))
        self.activity.done()


def day_buttons():
    today = datetime.today()
    prev_day = prev_weekday(today)
    prev_day_name = 'Eilen' if today - timedelta(days=1) == prev_day else 'Edellinen arkipäivä'
    prev_day_text = f'{prev_day_name} {d_fi_name(prev_day)} {d_fi(prev_day)}'
    return [[
        InlineKeyboardButton(text=prev_day_text, callback_data=str(prev_day)),
        InlineKeyboardButton(text=f'Tänään {d_fi_name(today)} {d_fi(today)}', callback_data=str(today)),
    ]]
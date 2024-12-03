from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.daily_question.message_utils import dq_saved_msg
from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.utils_common import prev_weekday, has_no, dt_at_midday, fi_short_day_name, fitzstr_from, \
    parse_dt_str_to_utctzstr
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

    async def execute_state(self):
        markup = InlineKeyboardMarkup(day_buttons())
        await self.send_or_update_host_message(self.reply_text, markup)

    async def preprocess_reply_data_hook(self, text: str) -> str | None:
        date = parse_dt_str_to_utctzstr(text)
        if has_no(date):
            reply_text = f'{self.reply_text}\n\n{date_invalid_format_text}'
            await self.send_or_update_host_message(reply_text)
        return date

    async def handle_response(self, update: Update, response_data: str, context: CallbackContext = None):
        utctzdt = dt_at_midday(datetime.fromisoformat(response_data))
        if utctzdt.date() <= self.prev_dq.date_of_question.date():  # both are utc
            reply_text = f'{self.reply_text}\n\nPäivämäärä voi olla aikaisintaan edellistä kysymystä seuraava päivä. ' \
                         f'Edellisen kysymyksen päivä on {fitzstr_from(self.prev_dq.date_of_question)}.'
            await self.send_or_update_host_message(reply_text)
            return  # given date was not valid

        # Inform user that the date has been confirmed and
        is_today = utctzdt.date() == self.current_dq.date_of_question.date()
        date_of_q_str = 'tämä päivä' if is_today else fitzstr_from(utctzdt)
        winner_set_str = f' ja kysyjä merkitty voittajaksi päivän {fitzstr_from(self.prev_dq.date_of_question)} kysymykseen.'
        reply_text = f'{dq_saved_msg(self.winner_set)} Kysymyksen päiväksi vahvistettu {date_of_q_str}' \
                     f'{winner_set_str if self.winner_set else "."}'

        self.current_dq.date_of_question = utctzdt
        self.current_dq.save()
        await self.send_or_update_host_message(reply_text, InlineKeyboardMarkup([]))
        await self.activity.done()


def day_buttons():
    fitz_today = datetime.now(fitz)
    today_text = f'Tänään {fi_short_day_name(fitz_today)} {fitzstr_from(fitz_today)}'

    prev_day = prev_weekday(fitz_today)
    prev_day_name = 'Eilen' if fitz_today - timedelta(days=1) == prev_day else 'Edellinen arkipäivä'
    prev_day_text = f'{prev_day_name} {fi_short_day_name(prev_day)} {fitzstr_from(prev_day)}'
    # Buttons are on top of each other (on their own rows)
    return [
        [InlineKeyboardButton(text=prev_day_text, callback_data=str(prev_day))],
        [InlineKeyboardButton(text=today_text, callback_data=str(fitz_today))]
    ]


date_formats_text = 'Tuetut formaatit ovat \'vvvv-kk-pp\', \'pp.kk.vvvv\' ja \'kk/pp/vvvv\'.'
date_invalid_format_text = f'Antamasi päivämäärä ei ole tuettua muotoa. {date_formats_text}'

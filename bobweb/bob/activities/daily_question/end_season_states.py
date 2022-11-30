from datetime import datetime

from pytz import utc
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState, cancel_button
from bobweb.bob.activities.command_activity import date_invalid_format_text, parse_dt_str_to_utctzstr
from bobweb.bob.utils_common import split_to_chunks, has_no, has, fitzstr_from, fi_short_day_name, fitz_from
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion


class SetLastQuestionWinnerState(ActivityState):
    def execute_state(self):
        chat_id = self.activity.host_message.chat_id
        target_datetime = self.activity.host_message.date  # utc
        season = database.find_active_dq_season(chat_id, target_datetime).first()
        last_dq = database.get_all_dq_on_season(season.id).first()
        if has_no(last_dq):
            self.remove_season_without_dq(season)
            return

        last_dq_answers = database.find_answers_for_dq(last_dq.id)
        if has_no(last_dq_answers):
            reply_text = build_msg_text_body(1, 3, end_season_no_answers_for_last_dq)
            markup = InlineKeyboardMarkup(season_end_confirm_end_buttons())
            self.activity.reply_or_update_host_message(reply_text, markup)
            return

        for answer in last_dq_answers:
            if answer.is_winning_answer:
                self.activity.change_state(SetSeasonEndDateState())
                return

        reply_text = build_msg_text_body(1, 3, lambda: end_date_last_winner_msg(last_dq.date_of_question))
        users_with_answer = list(set([a.answer_author.username for a in last_dq_answers]))  # to get unique values
        markup = InlineKeyboardMarkup(season_end_last_winner_buttons(users_with_answer))
        self.activity.reply_or_update_host_message(reply_text, markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == cancel_button.callback_data:
            self.activity.reply_or_update_host_message(end_season_cancelled)
            self.activity.done()
        if response_data == '/end_anyway':
            self.activity.change_state(SetSeasonEndDateState())
        else:
            tg_user = database.get_telegram_user_by_name(response_data).get()
            self.activity.change_state(SetSeasonEndDateState(tg_user.id))

    def remove_season_without_dq(self, season: DailyQuestionSeason):
        season.delete()
        reply_test = build_msg_text_body(1, 1, 'Ei esitettyjä kysymyksiä kauden aikana, '
                                               'joten kausi poistettu kokonaan.')
        self.activity.reply_or_update_host_message(reply_test)
        self.activity.done()


class SetSeasonEndDateState(ActivityState):
    def __init__(self, last_win_user_id=None):
        super().__init__()
        self.last_win_user_id = last_win_user_id
        self.season = None
        self.last_dq = None

    def execute_state(self):
        chat_id = self.activity.host_message.chat_id
        self.season: DailyQuestionSeason = database.find_active_dq_season(chat_id, self.activity.host_message.date).first()  # utc
        self.last_dq: DailyQuestion = database.get_all_dq_on_season(self.season.id).first()

        reply_text = build_msg_text_body(2, 3, end_date_msg)
        markup = InlineKeyboardMarkup(season_end_date_buttons(self.last_dq.date_of_question))
        self.activity.reply_or_update_host_message(reply_text, markup)

    def preprocess_reply_data(self, text: str) -> str | None:
        date = parse_dt_str_to_utctzstr(text)
        if has_no(date):
            reply_text = build_msg_text_body(2, 3, date_invalid_format_text)
            self.activity.reply_or_update_host_message(reply_text)
        return date

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == cancel_button.callback_data:
            self.activity.reply_or_update_host_message(end_season_cancelled)
            self.activity.done()
            return
        utctd = datetime.fromisoformat(response_data)
        if utctd.date() == datetime.now().date():
            # If user has chosen today, use host message's datetime as it's more accurate
            utctd = self.activity.host_message.date

        # Check that end date is at same or after last dq date
        if utctd.date() < self.last_dq.date_of_question.date():  # utc
            reply_text = build_msg_text_body(2, 3, get_end_date_must_be_same_or_after_last_dq(self.last_dq.date_of_question))
            self.activity.reply_or_update_host_message(reply_text)
            return  # Inform user that date has to be same or after last dq's date of question

        # Update Season to have end date
        self.season.end_datetime = utctd
        self.season.save()

        # Update given users answer to the last question to be winning one
        if has(self.last_win_user_id):
            answer = database.find_answer_by_user_to_dq(self.last_dq.id, self.last_win_user_id).first()
            answer.is_winning_answer = True
            answer.save()
        self.activity.change_state(SeasonEndedState(utctd))


class SeasonEndedState(ActivityState):
    def __init__(self, utctztd_end):
        super().__init__()
        self.utctztd_end = utctztd_end

    def execute_state(self):
        reply_text = build_msg_text_body(3, 3, lambda: get_season_ended_msg(self.utctztd_end))
        self.activity.reply_or_update_host_message(reply_text, InlineKeyboardMarkup([]))
        self.activity.done()


def season_end_last_winner_buttons(usernames: list[str]):
    user_buttons = [cancel_button] + [InlineKeyboardButton(text=name, callback_data=name) for name in usernames]
    return split_to_chunks(user_buttons, 3)


def season_end_confirm_end_buttons():
    return [[
        cancel_button,
        InlineKeyboardButton(text='Kyllä, päätä kausi', callback_data='/end_anyway')
    ]]


def season_end_date_buttons(last_dq_dt: datetime):
    utc_now = datetime.now(utc)
    # Edge case, where user has asked next days question and then decides to end season for some reason
    if has(last_dq_dt) and last_dq_dt > utc_now:
        end_date_button = InlineKeyboardButton(text=f'{fi_short_day_name(fitz_from(utc_now))}{fitzstr_from(last_dq_dt)}',
                                               callback_data=str(last_dq_dt))
    else:
        end_date_button = InlineKeyboardButton(text=f'Tänään ({fitzstr_from(utc_now)})',
                                               callback_data=str(utc_now))
    return [[cancel_button, end_date_button]]


def get_activity_heading(step_number: int, number_of_steps: int):
    return f'[Lopeta kysymysausi ({step_number}/{number_of_steps})]'


def end_date_last_winner_msg(dq_datetime: datetime):
    return f'Valitse ensin edellisen päivän kysymyksen ({fitzstr_from(dq_datetime)}) voittaja alta.'


end_date_msg = f'Valitse kysymyskauden päättymispäivä alta tai anna se vastaamalla tähän viestiin.'


def get_end_date_must_be_same_or_after_last_dq(last_dq_date_of_question: datetime):
    return f'Kysymyskausi voidaan merkitä päättyneeksi aikaisintaan viimeisen esitetyn päivän kysymyksen päivänä. ' \
           f'Viimeisin kysymys esitetty {fitzstr_from(last_dq_date_of_question)}.'


end_season_cancelled = 'Selvä homma, kysymyskauden päättäminen peruutettu.'
end_season_no_answers_for_last_dq = 'Viimeiseen päivän kysymykseen ei ole lainkaan vastauksia, eikä näin ollen ' \
                                          'sen voittajaa voida määrittää. Jos lopetat kauden nyt, jää viimeisen ' \
                                          'kysymyksen voitto jakamatta. Haluatko varmasti päättää kauden?'


def get_season_ended_msg(utctztd_end: datetime):
    date_str = 'tänään' if datetime.now(utc).date() == utctztd_end.date() else fitzstr_from(utctztd_end)
    return f'Kysymyskausi merkitty päättyneeksi {date_str}. Voit aloittaa uuden kauden kysymys-valikon kautta.'


def build_msg_text_body(i: int, n: int, state_message_provider):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider()
    return f'{get_activity_heading(i, n)}\n' \
           f'------------------\n' \
           f'{state_msg}'

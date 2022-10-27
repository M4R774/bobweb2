from datetime import datetime

from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from bobweb.bob import database
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT
from bobweb.bob.utils_common import split_to_chunks, has_no, has
from bobweb.web.bobapp.models import DailyQuestionSeason


class SetLastQuestionWinnerState(ActivityState):
    def execute_state(self):
        chat_id = self.activity.host_message.chat_id
        target_datetime = self.activity.host_message.date
        season = database.find_dq_season(chat_id, target_datetime).get()
        last_dq = database.get_all_dq_on_season(season.id).first()
        if has_no(last_dq):
            self.remove_season_without_dq(season)
            return

        last_dq_answers = database.find_answers_for_dq(last_dq.id)
        if has_no(last_dq_answers):
            reply_text = build_msg_text_body(1, 3, end_season_no_answers_for_last_dq)
            markup = InlineKeyboardMarkup(season_end_confirm_end_buttons())
            self.activity.update_host_message_content(reply_text, markup)
            return

        for answer in last_dq_answers:
            if answer.is_winning_answer:
                self.activity.change_state(SetSeasonEndDateState())
                return

        reply_text = build_msg_text_body(1, 3, lambda: end_date_last_winner_msg(last_dq.date_of_question))
        users_with_answer = [a.answer_author.username for a in last_dq_answers]
        markup = InlineKeyboardMarkup(season_end_last_winner_buttons(users_with_answer))
        self.activity.update_host_message_content(reply_text, markup)

    def handle_response(self, response_data: str):
        if response_data == '/cancel':
            self.activity.update_host_message_content(end_season_cancelled)
            self.activity.done()
        if response_data == '/end_anyway':
            self.activity.change_state(SetSeasonEndDateState())
        else:
            tg_user = database.get_telegram_user_by_name(response_data).get()
            self.activity.change_state(SetSeasonEndDateState(tg_user.id))

    def remove_season_without_dq(self, season: DailyQuestionSeason):
        season.delete()
        reply_test = build_msg_text_body(1, 1, 'Ei esitettyjä kysymyskiä kauden aikana, '
                                               'joten kausi poistettu kokonaan.')
        self.activity.update_host_message_content(reply_test)
        self.activity.done()


class SetSeasonEndDateState(ActivityState):
    def __init__(self, last_win_user_id=None):
        super().__init__()
        self.last_win_user_id = last_win_user_id

    def execute_state(self):
        reply_text = build_msg_text_body(2, 3, end_date_msg)
        markup = InlineKeyboardMarkup(season_end_date_buttons())
        self.activity.update_host_message_content(reply_text, markup)

    def preprocess_reply_data(self, text: str) -> str:
        for date_format in ('%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y'):  # 2022-01-31, 31.01.2022, 01/31/2022
            try:
                return str(datetime.strptime(text, date_format))
            except ValueError:
                pass
        reply_text = build_msg_text_body(1, 3, end_date_invalid_format)
        self.activity.update_host_message_content(reply_text)

    def handle_response(self, response_data: str):
        if response_data == '/cancel':
            self.activity.update_host_message_content(end_season_cancelled)
            self.activity.done()
            return
        date_time_obj = datetime.fromisoformat(response_data)

        chat_id = self.activity.host_message.chat_id
        target_datetime = self.activity.host_message.date

        # Update Season to have end date
        season_query = database.find_dq_season(chat_id, target_datetime)
        season: DailyQuestionSeason = season_query.get()
        season.end_datetime = date_time_obj
        season.save()

        # Update given users answer to the last question to be winning one
        if has(self.last_win_user_id):
            last_dq = database.find_all_dq_in_season(chat_id, target_datetime).first()
            answer = database.find_answer_by_user_to_dq(last_dq.id, self.last_win_user_id).first()
            answer.is_winning_answer = True
            answer.save()
        self.activity.change_state(SeasonEndedState(date_time_obj))


class SeasonEndedState(ActivityState):
    def __init__(self, end_date):
        super().__init__()
        self.end_date = end_date

    def execute_state(self):
        reply_text = build_msg_text_body(3, 3, lambda: get_season_ended_msg(self.end_date))
        self.activity.update_host_message_content(reply_text, InlineKeyboardMarkup([[]]))
        self.activity.done()


def season_end_last_winner_buttons(usernames: list[str]):
    user_buttons = [InlineKeyboardButton(text=name, callback_data=name) for name in usernames]
    return split_to_chunks(user_buttons, 3)


def season_end_confirm_end_buttons():
    return [[
        InlineKeyboardButton(text='Peruuta', callback_data='/cancel'),
        InlineKeyboardButton(text='Kyllä, päätä kausi', callback_data='/end_anyway')
    ]]


def season_end_date_buttons():
    now = datetime.today()
    today = datetime(now.year, now.month, now.day)
    return [[
        InlineKeyboardButton(text=f'Peruute', callback_data='/cancel'),
        InlineKeyboardButton(text=f'Tänään ({today.strftime(FINNISH_DATE_FORMAT)})', callback_data=str(today)),
    ]]


def get_activity_heading(step_number: int, number_of_steps: int):
    return f'[Lopeta kysymysausi ({step_number}/{number_of_steps})]'


def end_date_last_winner_msg(dq_datetime: datetime):
    return f'Valitse ensimmäisenä edellisen päivän kysymyksen ({dq_datetime.strftime(FINNISH_DATE_FORMAT)}) ' \
           f'voittaja alta.'


end_date_msg = f'Valitse kysymyskauden päättymispäivä alta tai anna se vastaamalla tähän viestiin.'
end_date_formats = 'Tuetut formaatit ovat \'vvvv-kk-pp\', \'pp.kk.vvvv\' ja \'kk/pp/vvvv\'.'
end_date_invalid_format = f'Antamasi päivämäärä ei ole tuettua muotoa. {end_date_formats}'

end_season_cancelled = 'Selvä homma, kysymyskauden päättäminen peruutettu.'
end_season_no_answers_for_last_dq = 'Viimeiseen päivän kysymykseen ei ole lainkaan vastauksia, eikä näin ollen ' \
                                          'sen voittajaa voida määrittää. Jos lopetat kauden nyt, jää viimeisen ' \
                                          'kysymyksen voitto jakamatta. Haluatko varmasti päättää kauden?'

def get_season_ended_msg(end_date: datetime):
    today = datetime.today().date()
    if end_date.date() == today:
        date_string = 'tänään'
    else:
        date_string = today.strftime(FINNISH_DATE_FORMAT)
    return f'Kysymyskausi merkitty päättymään {date_string}. Voit aloittaa uuden kauden kysymys-valikon kautta.'


def build_msg_text_body(i: int, n: int, state_message_provider):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider()
    return f'{get_activity_heading(i, n)}\n' \
           f'------------------\n' \
           f'{state_msg}'

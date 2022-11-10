from datetime import datetime
from typing import List

from django.db.models import QuerySet
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton

from bobweb.bob import database, command_service
from bobweb.bob.activities.activity_state import ActivityState
from bobweb.bob.activities.command_activity import CommandActivity
from bobweb.bob.activities.daily_question.end_season_states import SetLastQuestionWinnerState
from bobweb.bob.activities.daily_question.start_season_activity import StartSeasonActivity
from bobweb.bob.activities.daily_question.start_season_states import SetSeasonStartDateState, StartSeasonActivityState
from bobweb.bob.resources.bob_constants import FINNISH_DATE_FORMAT
from bobweb.bob.utils_common import has, has_no
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestionAnswer


class DQMainMenuState(ActivityState):
    def __init__(self, activity: CommandActivity = None, initial_update: Update = None):
        super().__init__()
        self.activity = activity
        self.initial_update = initial_update

    def execute_state(self):
        reply_text = dq_main_menu_text_body('Valitse toiminto alapuolelta')
        markup = InlineKeyboardMarkup(self.dq_main_menu_buttons())

        if self.activity.host_message is None:
            self.activity.host_message = self.initial_update.effective_message.reply_text(reply_text, reply_markup=markup)
        else:
            self.activity.update_host_message_content(reply_text, markup)

    def dq_main_menu_buttons(self):
        return [[
            InlineKeyboardButton(text='Info', callback_data='info'),
            InlineKeyboardButton(text='Kausi', callback_data='season'),
            # InlineKeyboardButton(text='Tilasto', callback_data='stats')
        ]]

    def handle_response(self, response_data: str):
        next_state: ActivityState | None = None
        match response_data:
            case 'info': next_state = DQInfoMessageState(self.activity)
            case 'season': next_state = DQSeasonsMenuState(self.activity)

        if next_state:
            self.activity.change_state(next_state)


class DQInfoMessageState(ActivityState):
    def execute_state(self):
        reply_text = dq_main_menu_text_body('Infoviesti tähän')
        markup = InlineKeyboardMarkup(self.buttons())
        self.activity.update_host_message_content(reply_text, markup)

    def buttons(self):
        return [[
            InlineKeyboardButton(text='<-', callback_data='back'),
            InlineKeyboardButton(text='Lisää tietoa', callback_data='more'),
            InlineKeyboardButton(text='Komennot', callback_data='commands')
        ]]

    def handle_response(self, response_data: str):
        extended_info_text = None
        match response_data:
            case 'back':
                self.activity.change_state(DQMainMenuState())
                return
            case 'more':
                extended_info_text = dq_main_menu_text_body('Infoviesti tähän\n\nTässä on vähän enemmän infoa')
            case 'commands':
                extended_info_text = dq_main_menu_text_body('Tässä tieto komennoista')
        self.activity.update_host_message_content(extended_info_text)


class DQSeasonsMenuState(ActivityState):
    def execute_state(self):
        seasons = database.find_dq_seasons_for_chat(self.activity.host_message.chat_id)
        if has(seasons):
            self.handle_has_seasons(seasons)
        else:
            self.handle_has_no_seasons()

    def handle_has_seasons(self, seasons: QuerySet):
        latest_season: DailyQuestionSeason = seasons.first()

        season_info = get_season_basic_info_text(latest_season)
        if latest_season.end_datetime is None:
            end_start_button = InlineKeyboardButton(text='Lopeta kausi', callback_data='end_season')
        else:
            end_start_button = InlineKeyboardButton(text='Ailoita kausi', callback_data='start_season')

        buttons = [[
            InlineKeyboardButton(text='<-', callback_data='back'),
            InlineKeyboardButton(text='Lisää tilastoa', callback_data='stats'),
            end_start_button
        ]]
        self.activity.update_host_message_content(season_info, InlineKeyboardMarkup(buttons))

    def handle_has_no_seasons(self):
        reply_text = dq_main_menu_text_body('Tähän chättiin ei ole vielä luotu kysymyskautta päivän kysymyksille')
        buttons = [[
            InlineKeyboardButton(text='<-', callback_data='back'),
            InlineKeyboardButton(text='Uusi kausi', callback_data='start_season')
        ]]
        self.activity.update_host_message_content(reply_text, InlineKeyboardMarkup(buttons))

    def handle_response(self, response_data: str):
        match response_data:
            case 'back':
                self.activity.change_state(DQMainMenuState())
                return
            case 'start_season':
                # Example of changing Activity to a different activity that has different base class
                host_message = self.activity.host_message
                self.activity.done()  # Mark current activity to be done
                self.activity = StartSeasonActivity()
                command_service.instance.add_activity(self.activity)  # Add to commandService current_activites
                self.activity.host_message = host_message
                self.activity.change_state(SetSeasonStartDateState())

            case 'end_season':
                # Example of keeping same activity but just changing its state
                self.activity.change_state(SetLastQuestionWinnerState())
            case 'commands':
                extended_info_text = dq_main_menu_text_body('Tässä tieto komennoista')
                self.activity.update_host_message_content(extended_info_text)


def get_season_basic_info_text(season: DailyQuestionSeason):
    questions = database.get_all_dq_on_season(season.id)
    winning_answers_on_season = database.find_answers_in_season(season.id).filter(is_winning_answer=True)

    most_wins_text = get_most_wins_text(winning_answers_on_season)

    conditional_end_date = ''
    season_state = 'Aktiivisen'
    if has(season.end_datetime):
        season_state = 'Edellisen'
        conditional_end_date = F'Kausi päättynyt: {season.end_datetime.strftime(FINNISH_DATE_FORMAT)}\n'

    return dq_main_menu_text_body(f'Kysymyskaudet\n'
                                  f'{season_state} kauden nimi: {season.season_name}\n'
                                  f'Kausi alkanut: {season.start_datetime.strftime(FINNISH_DATE_FORMAT)}\n'
                                  f'{conditional_end_date}'
                                  f'Kysymyksiä kysytty: {questions.count()}\n'
                                  f'{most_wins_text}')


def get_most_wins_text(winning_answers: List[DailyQuestionAnswer]) -> str:
    if has_no(winning_answers):
        return ''

    # https://dev.to/mojemoron/pythonic-way-to-aggregate-or-group-elements-in-a-list-using-dict-get-and-dict-setdefault-49cb
    wins_by_users = {}
    for answer in winning_answers:
        name = answer.answer_author.username
        wins_by_users[name] = wins_by_users.get(name, 0) + 1
    print(wins_by_users)

    max_wins = max([x for x in list(wins_by_users.values())])
    users_with_most_wins = [user for (user, wins) in wins_by_users.items() if wins == max_wins]

    if len(users_with_most_wins) <= 3:
        return f'Eniten voittoja ({max_wins}): {", ".join(users_with_most_wins)}'
    else:
        return f'Eniten voittoja ({max_wins}): {len(users_with_most_wins)} käyttäjää'


def dq_main_menu_text_body(state_message_provider):
    state_msg = state_message_provider
    if callable(state_message_provider):
        state_msg = state_message_provider()
    return f'-- Päivän kysymys --\n' \
           f'------------------\n' \
           f'{state_msg}'

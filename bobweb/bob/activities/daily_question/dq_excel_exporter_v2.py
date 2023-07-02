import io
import re
from datetime import datetime
from enum import Enum
from typing import List, Tuple, Dict

import xlsxwriter
from telegram.ext import CallbackContext
from xlsxwriter import Workbook
from xlsxwriter.utility import xl_rowcol_to_cell, xl_col_to_name, xl_cell_to_rowcol
from xlsxwriter.worksheet import Worksheet

from bobweb.bob import database
from bobweb.bob.resources.bob_constants import fitz, FILE_NAME_DATE_FORMAT, ISO_DATE_FORMAT
from bobweb.bob.utils_common import excel_date, excel_time, has
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion, TelegramUser, DailyQuestionAnswer

"""
Tools for writing daily question statistics to an excel sheet
NOTE Uses same coordinates than excel, so rows start from index 1
"""

class DQ_COLUMND_HEADERS(Enum):
    NUMERO = 'Numero'
    LUOTU = 'Luotu'
    PAIVA = 'Päivä'
    LINKKI_VIESTI = 'Linkki viestiin'
    KYSYJÄ = 'Kysyjä'
    KYSYMYS = 'Kysymys'
    VASTAUS_LKM = 'Vastaus lkm'
    OIKEA_VASTAUS = 'Oikea vastaus'
    VOITTAJA = 'Voittaja'


def get_headers_str_list():
    return [header[1].value for header in enumerate(DQ_COLUMND_HEADERS)]


class UsersAnswer:
    """ Answers is concatenated version of all users answers"""
    def __init__(self, user_id: int, answers: str, is_winning: bool, order: int):
        self.user_id = user_id
        self.answers = answers
        self.is_winning = is_winning
        self.order = order


# Heading and user stats bar height in cells
HEADING_HEIGHT = 7
INFO_WIDTH = 9
TABLE_NAME = 'dq_data'

# Constant style definitions
BOLD = {'bold': True}
WRAPPED = {'text_wrap': True, 'valign': 'top'}
BORDER_LEFT = {'left': 2, 'border_color': 'black'}
BORDER_RIGHT = {'right': 2, 'border_color': 'black'}
BG_GREY = {'bg_color': '#E7E6E6'}
BG_LIGHTBLUE = {'bg_color': '#DAEEF3'}
BG_LIGHORANGE = {'bg_color': '#FDE9D9'}


def send_dq_stats_excel_v2(chat_id: int, season_id: int , context: CallbackContext = None):
    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output)
    sheet: Worksheet = wb.add_worksheet("Kysymystilastot")

    form_and_write_sheet(wb, sheet, chat_id, season_id)
    wb.close()
    output.seek(0)

    today_date_iso_str = datetime.now(fitz).date().strftime(ISO_DATE_FORMAT)
    file_name = f'{today_date_iso_str}_daily_question_stats.xlsx'
    context.bot.send_document(chat_id=chat_id, document=output, filename=file_name)


def form_and_write_sheet(wb: Workbook, sheet: Worksheet, chat_id: int, season_id):
    all_seasons: List[DailyQuestionSeason] = database.get_seasons_for_chat(chat_id)
    season = next((season for season in all_seasons if season.id == season_id), None)

    # All users with answers recorded in the season
    users_with_answers = database.find_users_with_answers_in_season(season.id)

    last_table_row = HEADING_HEIGHT + 1 + season.dailyquestion_set.all().count()
    last_table_col = xl_col_to_name(INFO_WIDTH + len(users_with_answers) * 3 - 1)

    write_heading_with_information(wb, sheet, season)
    user_column_headings = write_user_boxes(wb, sheet, users_with_answers)

    # Setup table
    columns = [{'header': header} for header in get_headers_str_list() + user_column_headings]
    table_options = {
        'name': TABLE_NAME,
        'header_row': True,
        'style': 'Table Style Light 13',
        'columns': columns}
    sheet.add_table(f'A{HEADING_HEIGHT + 1}:{last_table_col}{last_table_row}', table_options)

    write_daily_question_information(wb, sheet, season, users_with_answers)


def write_heading_with_information(wb: Workbook, sheet: Worksheet, season: DailyQuestionSeason):
    """ Writes heading and info to the excel sheet. """
    # question_result_set = season.dailyquestion_set.all()
    # question_count = question_result_set.count()

    bg_gray = wb.add_format(BG_GREY)
    bg_gray_bold = wb.add_format({**BOLD, **BG_GREY})
    bg_gray_wrapped = wb.add_format({**WRAPPED, **BG_GREY})

    sheet.merge_range('A1:I1', f'BOBin päivän kysymys -tilastot kaudelta {season.season_name}', bg_gray_bold)
    sheet.write('A2', f'Alkanut', bg_gray_bold)
    sheet.write('B2', excel_date(season.start_datetime), bg_gray)
    sheet.write_blank('C2', '', bg_gray_bold)
    sheet.write('D2', f'Päättynyt', bg_gray_bold)
    sheet.write('E2', excel_date(season.end_datetime) if season.end_datetime else '-', bg_gray)
    sheet.write_blank('F2', '', bg_gray_bold)
    sheet.write_blank('G2', '', bg_gray_bold)
    sheet.write('H2', 'Kysymyksiä:', bg_gray_bold)
    sheet.write_formula('I2', f'=COUNTA({TABLE_NAME}[{DQ_COLUMND_HEADERS.KYSYMYS.value}])', bg_gray)

    info_text = "Oranssilla taustalla oleva vastaus on voittaja kyseiseltä kierrokselta.\nYksityisviesteillä tai " \
                "muilla manetelmillä kuin telegramin viestivastauksina (reply) annettuja vastauksia ei ole huomioitu " \
                "automaattisesti. Viiva tarkoittaa ettei kilpailija vastannut kyssäriin. Hyvä ihmiskäyttäjä, " \
                "täytäthän sarakkeen \"Oikea vastaus\" itse."
    sheet.merge_range(f'A3:I{HEADING_HEIGHT}', info_text, bg_gray_wrapped)

    # Write daily question section headings
    row = HEADING_HEIGHT + 1
    for i, header in enumerate(get_headers_str_list()):
        sheet.write(row, 1, header)

    sheet.set_column(1, 1, width=13)  # Luotu
    sheet.set_column(2, 2, width=10)  # Kysymyksen päivä
    sheet.set_column(4, 4, width=13)  # Kysyjä
    sheet.set_column(5, 5, width=50)  # Kysymys
    sheet.set_column(7, 7, width=13)  # Voittaja


def write_user_boxes(wb: Workbook, sheet: Worksheet, users_with_answers: List[TelegramUser]) -> List[str]:
    """ Writes users details info box for each user. Returns all headings as str list"""
    # Border Formats
    name_heading_format = wb.add_format({**BG_LIGHTBLUE, **BORDER_LEFT, **BORDER_RIGHT, 'align': 'center'})
    bg_light_blue_bl = wb.add_format({**BG_LIGHTBLUE, 'left': 2, 'left_color': 'black'})
    bg_light_blue_br = wb.add_format({**BG_LIGHTBLUE, 'right': 2, 'right_color': 'black'})
    percentage_format = wb.add_format({**BG_LIGHTBLUE, 'right': 2, 'right_color': 'black', 'num_format': '0.00%'})

    column_headings = []
    for i, user in enumerate(users_with_answers):
        initials = get_user_initials(user)
        col = INFO_WIDTH + (i * 3)

        # Add summary labels
        sheet.merge_range(0, col, 0, col + 2, str(user), name_heading_format)
        sheet.merge_range(1, col, 1, col + 1, 'Vastauksia:', bg_light_blue_bl)
        sheet.merge_range(2, col, 2, col + 1, 'Voittoja:', bg_light_blue_bl)
        sheet.merge_range(3, col, 3, col + 1, 'Konversioprosentti', bg_light_blue_bl)
        sheet.merge_range(4, col, 4, col + 1, 'Keskiarvo-vastausvuoro:', bg_light_blue_bl)
        sheet.merge_range(5, col, 5, col + 1, 'Keskiarvotarkkuus:', bg_light_blue_bl)
        sheet.merge_range(6, col, 6, col + 1, 'Mediaanitarkkuus:', bg_light_blue_bl)

        # Add summary formulas
        formula_col = col + 2
        sheet.write_formula(1, formula_col, f'=COUNTIF({TABLE_NAME}[{initials} vastaus],"<>-")', bg_light_blue_br)
        sheet.write_formula(2, formula_col, f'=COUNTIF({TABLE_NAME}[Voittaja],"{initials}")', bg_light_blue_br)
        conversion_formula = f'={xl_rowcol_to_cell(2, formula_col)}/{xl_rowcol_to_cell(1, formula_col)}'
        sheet.write_formula(3, formula_col, conversion_formula, percentage_format)
        sheet.write_formula(4, formula_col, f'=AVERAGE({TABLE_NAME}[{initials} vuoro])', bg_light_blue_br)
        sheet.write_formula(5, formula_col, f'=AVERAGE({TABLE_NAME}[{initials} tarkkuus])', bg_light_blue_br)
        sheet.write_formula(6, formula_col, f'=MEDIAN({TABLE_NAME}[{initials} tarkkuus])', bg_light_blue_br)

        # Add question answer labels to sheet and to the list of user headings
        sheet.write(7, col, f'{initials} vastaus')
        column_headings.append(f'{initials} vastaus')
        sheet.write(7, col + 1, f'{initials} tarkkuus')
        column_headings.append(f'{initials} tarkkuus')
        sheet.write(7, col + 2, f'{initials} vuoro')
        column_headings.append(f'{initials} vuoro')

    return column_headings


def write_daily_question_information(wb: Workbook, sheet: Worksheet, season: DailyQuestionSeason, users_with_answers: List[TelegramUser]):
    """ Writes question information to the excel sheet. """
    questions: List[DailyQuestion] = list(season.dailyquestion_set.all())
    format_date = wb.add_format({'num_format': 'dd.mm.yy'})
    format_datetime = wb.add_format({'num_format': 'dd.mm.yy hh:mm'})

    for i, dq in enumerate(questions):
        all_answers = list(dq.dailyquestionanswer_set.all())
        # List of answer objects where each answer contains text content of all users answer messages
        # Each user is present only once even though they might have given answer with multiple messages
        users_answers_to_dq = form_answers_list(all_answers)

        row = HEADING_HEIGHT + 2 + i
        sheet.write_number(f'A{row}', i + 1)
        sheet.write_number(f'B{row}', excel_time(dq.created_at), format_datetime)
        sheet.write_number(f'C{row}', excel_date(dq.date_of_question), format_date)
        sheet.write(f'D{row}', f'https://t.me/c/{season.chat_id}/{dq.message_id}')
        sheet.write(f'E{row}', dq.question_author.username or dq.question_author.first_name)

        # Content in merged cell. "#päivänkysymys" is removed
        content = re.sub(r'#päivänkysymys\s*', '', dq.content)
        # sheet.write(f'F{row}', content, wb.add_format(WRAPPED))
        sheet.write(f'F{row}', content)
        sheet.write_number(f'G{row}', len(users_answers_to_dq))
        sheet.write_blank(f'H{row}', '')

        # Add winner of the question. Either author of the next question
        # or the winner of the last question if last question of the season and the season has ended
        is_last_question = i == len(questions) - 1
        if has(season.end_datetime) and is_last_question:
            # Try to find winning answer if that has been marked
            winner = next((x for x in all_answers if x.is_winning_answer), None)
        elif is_last_question:
            winner = None
        else:
            winner = questions[i + 1].question_author

        if winner:
            sheet.write(f'I{row}', get_user_initials(winner))

        row_0_indexed = row - 1
        # Now write each answer to the question
        for j, user in enumerate(users_with_answers):
            column = INFO_WIDTH + j * 3
            users_answer: UsersAnswer = users_answers_to_dq.get(user.id)

            if users_answer is None:
                sheet.write(row_0_indexed, column, '-', wb.add_format(BORDER_LEFT))
                sheet.write(row_0_indexed, column + 2, '-', wb.add_format(BORDER_RIGHT))
            else:
                bg_props = BG_LIGHORANGE if users_answer.is_winning else {}
                sheet.write(row_0_indexed, column, users_answer.answers, wb.add_format({**BORDER_LEFT, **bg_props}))
                sheet.write_blank(row_0_indexed, column + 1, '', wb.add_format(bg_props))
                sheet.write(row_0_indexed, column + 2, users_answer.order, wb.add_format({**BORDER_RIGHT, **bg_props}))


def form_answers_list(answers: List[DailyQuestionAnswer]) -> Dict[int, UsersAnswer]:
    answers.sort(key=lambda answer: answer.created_at, reverse=True)

    # Results are set to a dict with user_id as the key, and UserAnswer object as value
    result_dict: Dict[int, UsersAnswer] = dict()
    # User might have multiple answers to same dq, order is incremented only when new user is added to the dict
    user_order = 0
    for a in answers:
        if result_dict.get(a.answer_author.id):
            result_dict.get(a.answer_author.id).answers += '\n\n' + a.content
        else:
            user_order += 1
            result_dict[a.answer_author.id] = UsersAnswer(a.answer_author.id, a.content, a.is_winning_answer, user_order)
    return result_dict


def write_values_to_row(sheet: Worksheet, values: List[str | tuple[str, int]], row: int, start_col: str):
    for i, value in enumerate(values):
        col = chr(ord(start_col) + i)
        sheet.write(f'{col}{row}', value)


def get_user_initials(user: TelegramUser):
    return str(user)

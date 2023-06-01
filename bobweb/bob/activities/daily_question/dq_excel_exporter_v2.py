import io
import re
from datetime import datetime
from typing import List

import xlsxwriter
from telegram.ext import CallbackContext
from xlsxwriter import Workbook
from xlsxwriter.utility import xl_rowcol_to_cell, xl_col_to_name, xl_cell_to_rowcol
from xlsxwriter.worksheet import Worksheet

from bobweb.bob import database
from bobweb.bob.resources.bob_constants import FILE_NAME_DATE_FORMAT, fitz
from bobweb.bob.utils_common import excel_date, excel_time, has
from bobweb.web.bobapp.models import DailyQuestionSeason, DailyQuestion, TelegramUser

"""
Tools for writing daily question statistics to an excel sheet
NOTE Uses same coordinates than excel, so rows start from index 1
"""

# Heading and user stats bar height in cells
HEADING_HEIGHT = 7
INFO_WIDTH = 8
TABLE_NAME = 'dq_data'

# Constant style definitions
BOLD = {'bold': True}
WRAPPED = {'text_wrap': True, 'valign': 'top'}
BG_GREY = {'bg_color': '#E7E6E6'}
BG_LIGHTBLUE = {'bg_color': '#DDEBF7'}
BG_BLUE = {'bg_color': '#E7E6E6'}


def send_dq_stats_excel_v2(chat_id: int, context: CallbackContext = None):
    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output)
    sheet: Worksheet = wb.add_worksheet("Kysymystilastot")

    form_and_write_sheet(wb, sheet, chat_id)
    wb.close()
    output.seek(0)

    today_date_iso_str = datetime.now(fitz).date().strftime(FILE_NAME_DATE_FORMAT)
    file_name = f'{today_date_iso_str}_daily_question_stats.xlsx'
    context.bot.send_document(chat_id=chat_id, document=output, filename=file_name)


def form_and_write_sheet(wb: Workbook, sheet: Worksheet, chat_id: int):
    all_seasons: List[DailyQuestionSeason] = database.get_seasons_for_chat(chat_id)

    # For now, only one season
    season = all_seasons[-1]

    # All users with answers recorded in the season
    users_with_answers = database.find_users_with_answers_in_season(season.id)

    last_table_row = HEADING_HEIGHT + 1 + season.dailyquestion_set.all().count()
    last_table_col = xl_col_to_name(INFO_WIDTH + len(users_with_answers) * 3)

    # Setup table
    table_options = {'name': TABLE_NAME, 'header_row': True, 'style': 'Table Style Light 13'}
    sheet.add_table(f'A{HEADING_HEIGHT + 1}:{last_table_col}{last_table_row}', table_options)

    write_heading_with_information(wb, sheet, season)
    write_user_boxes(wb, sheet, users_with_answers)

    write_daily_question_information(wb, sheet, season)

    # result_array = [excel_sheet_headings]  # Initiate result array with headings
    # for s in all_seasons:
    #     end_dt_str = excel_time(s.end_datetime) if has(s.end_datetime) else ''
    #     season = [s.season_name, excel_time(s.start_datetime), end_dt_str]
    #     all_questions: List[DailyQuestion] = list(s.dailyquestion_set.all())
    #     for q in all_questions:
    #         question = [excel_date(q.date_of_question), excel_time(q.created_at), q.question_author, q.content]
    #         all_answers: List[DailyQuestionAnswer] = list(q.dailyquestionanswer_set.all())
    #         for a in all_answers:
    #             answer = [excel_time(a.created_at), a.answer_author, a.content


def write_heading_with_information(wb: Workbook, sheet: Worksheet, season: DailyQuestionSeason):
    """ Writes heading and info to the excel sheet. """
    question_result_set = season.dailyquestion_set.all()
    question_count = question_result_set.count()

    bg_gray = wb.add_format(BG_GREY)
    bg_gray_bold = wb.add_format({**BOLD, **BG_GREY})
    bg_gray_wrapped = wb.add_format({**WRAPPED, **BG_GREY})

    sheet.merge_range('A1:H1', f'BOBin päivän kysymys -tilastot kaudelta {season.season_name}', bg_gray_bold)
    sheet.write('A2', f'Alkanut', bg_gray_bold)
    sheet.write('B2', excel_date(season.start_datetime), bg_gray)
    sheet.write_blank('C2', '', bg_gray_bold)
    sheet.write('D2', f'Päättynyt', bg_gray_bold)
    sheet.write('E2', excel_date(season.end_datetime) if season.end_datetime else '-', bg_gray)
    sheet.write_blank('F2', '', bg_gray_bold)
    sheet.write('G2', 'Kysymyksiä:', bg_gray_bold)
    sheet.write('H2', str(question_count), bg_gray)

    info_text = "Keltaisella merkityt vastaukset on voittaja kyseiseltä kierrokselta.\nPrivana lähetettyjä " \
                "vastausten huomiointi on rajallista ja vain osittain onnistunutta. Tarkkuus vastaukselle on " \
                "laskettu, jos kysymys sen sallii (absoluuttinen etäisyys oikeasta vastauksesta / oma helppo " \
                "sovellus / kysyjän ilmoittama). Muussa tapauksessa tarkkuus-solu on jätetty tyhjäksi. Viiva " \
                "tarkoittaa ettei kilpailija vastannut kyssäriin, huom kysyjärooli voiton jälkeen."
    sheet.merge_range(f'A3:H{HEADING_HEIGHT}', info_text, bg_gray_wrapped)

    # Write daily question section headings
    row = HEADING_HEIGHT + 1
    sheet.write(f'A{row}', 'Numero')
    sheet.write(f'B{row}', 'Luotu')
    sheet.write(f'C{row}', 'Päivä')
    sheet.write(f'D{row}', 'Linkki viestiin')
    sheet.write(f'E{row}', 'Kysyjä')
    sheet.write(f'F{row}', 'Kysymys')
    question_col_index = xl_cell_to_rowcol(f'F{row}')[1]
    sheet.set_column(question_col_index, question_col_index, width=34, cell_format=wb.add_format(WRAPPED))
    sheet.write(f'G{row}', 'Vastaus lkm')
    sheet.write(f'H{row}', 'Voittaja')


def write_user_boxes(wb: Workbook, sheet: Worksheet, users_with_answers: List[TelegramUser]):
    bg_light_blue = wb.add_format(BG_LIGHTBLUE)

    for i, user in enumerate(users_with_answers):
        initials = get_user_initials(user)
        col = INFO_WIDTH + (i * 3)

        # Add summary labels
        sheet.merge_range(0, col, 0, col + 2, str(user), bg_light_blue.set_text_h_align('center'))
        sheet.merge_range(1, col, 1, col + 1, 'Vastauksia:', bg_light_blue)
        sheet.merge_range(2, col, 2, col + 1, 'Voittoja:', bg_light_blue)
        sheet.merge_range(3, col, 3, col + 1, 'Konversioprosentti', bg_light_blue)
        sheet.merge_range(4, col, 4, col + 1, 'Keskiarvo-vastausvuoro:', bg_light_blue)
        sheet.merge_range(5, col, 5, col + 1, 'Keskiarvotarkkuus:', bg_light_blue)
        sheet.merge_range(6, col, 6, col + 1, 'Mediaanitarkkuus:', bg_light_blue)

        # Add summary formulas
        formula_col = col + 2
        sheet.write_formula(1, formula_col, f'=COUNTIF({TABLE_NAME}[{initials} vastaus];"<>-")', bg_light_blue)
        sheet.write_formula(2, formula_col, f'=COUNTIF({TABLE_NAME}[Voittaja];"{initials}")', bg_light_blue)
        sheet.write_formula(3, formula_col, f'={xl_rowcol_to_cell(2, formula_col)}/{xl_rowcol_to_cell(1, formula_col)}', bg_light_blue)
        sheet.write_formula(4, formula_col, f'=AVERAGE({TABLE_NAME}[{initials} vuoro])', bg_light_blue)
        sheet.write_formula(5, formula_col, f'=AVERAGE({TABLE_NAME}[{initials} tarkkuus])', bg_light_blue)
        sheet.write_formula(6, formula_col, f'=MEDIAN({TABLE_NAME}[{initials} tarkkuus])', bg_light_blue)

        # Add question answer labels
        sheet.write(7, col, f'{initials} vastaus')
        sheet.write(7, col + 1, f'{initials} tarkkuus')
        sheet.write(7, col + 2, f'{initials} vuoro')




def write_daily_question_information(wb: Workbook, sheet: Worksheet, season: DailyQuestionSeason):
    """ Writes question information to the excel sheet. """
    questions: List[DailyQuestion] = list(season.dailyquestion_set.all())

    for i, q in enumerate(questions):
        row = HEADING_HEIGHT + 2 + i
        # dq_details = [
        #     i + 1,
        #     excel_date(q.date_of_question),
        #     excel_time(q.created_at),
        #     f'https://t.me/c/{chat_id}/{q.message_id}',  # Link is works only in super groups
        #     q.question_author.username,
        #     q.content,
        #     q.dailyquestionanswer_set.count()
        # ]
        # write_values_to_row(sheet, dq_details, row, start_col)
        sheet.write(f'A{row}', i + 1)
        sheet.write(f'B{row}', excel_time(q.created_at))
        sheet.write(f'C{row}', excel_date(q.date_of_question))
        sheet.write(f'D{row}', f'https://t.me/c/{season.chat_id}/{q.message_id}')
        sheet.write(f'E{row}', q.question_author.username or q.question_author.first_name)

        # Content in merged cell. "#päivänkysymys" is removed
        content = re.sub(r'#päivänkysymys\s*', '', q.content)
        sheet.write(f'F{row}', content, wb.add_format(WRAPPED))
        sheet.write(f'G{row}', q.dailyquestionanswer_set.count())

        # Add winner of the question. Either author of the next question
        # or the winner of the last question if last question of the season and the season has ended
        is_last_question = i == len(questions) - 1
        if has(season.end_datetime) and is_last_question:
            winner = q.dailyquestionanswer_set.filter(is_winning_answer=True).first().answer_author
        elif is_last_question:
            winner = None
        else:
            winner = questions[i + 1].question_author

        if winner:
            sheet.write(f'H{row}', get_user_initials(winner))


def write_values_to_row(sheet: Worksheet, values: List[str | tuple[str, int]], row: int, start_col: str):
    for i, value in enumerate(values):
        col = chr(ord(start_col) + i)
        sheet.write(f'{col}{row}', value)


def get_user_initials(user: TelegramUser):
    return str(user)

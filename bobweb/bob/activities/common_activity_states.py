from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bobweb.bob.activities.activity_state import ActivityState

# Buttons labels for paginator skip to start and skipt to end buttons
paginator_skip_to_start_label = '<<'
paginator_skip_to_end_label = '>>'


class ContentPaginationState(ActivityState):
    """
    Generi activity state for any paginated content. Useful for example if message content is longer than Telegrams
    allowed 4096 characters. Indexes start from 0, labels start from 1.
    """
    def __init__(self, pages: List[str], current_page: int = 0):
        super().__init__()
        self.pages = pages
        self.current_page = current_page

    def execute_state(self):
        if len(self.pages) > 1:
            pagination_labels = create_page_labels(len(self.pages), self.current_page)
            buttons = [InlineKeyboardButton(text=label, callback_data=label) for label in pagination_labels]
            markup = InlineKeyboardMarkup([buttons])
            heading = create_page_heading(len(self.pages), self.current_page)
        else:
            markup = None
            heading = ''
        page_content = heading + self.pages[self.current_page]
        self.activity.reply_or_update_host_message(page_content, markup=markup)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == paginator_skip_to_start_label:
            next_page = 0
        elif response_data == paginator_skip_to_end_label:
            next_page = len(self.pages) - 1
        else:
            next_page = int(response_data.replace('[', '').replace(']', '')) - 1

        self.current_page = next_page
        self.execute_state()


def create_page_labels(total_pages: int, current_page: int, max_buttons: int = 7) -> List[str]:
    """ Creates buttons labels for simple paginator element. Check tests for examples. Works like standard paginator
        element where buttons are shown up to defined max_buttons count. Current page is surrounded '[x]'"""
    if total_pages == 1:
        return ['[1]']

    half_max_buttons = max_buttons // 2
    if current_page - half_max_buttons <= 0:
        start = 0
        end = min(total_pages, max_buttons)
    elif current_page + half_max_buttons >= total_pages:
        end = total_pages
        start = max(0, total_pages - max_buttons)
    else:
        start = current_page - half_max_buttons
        end = start + max_buttons

    # First button is either '1' or '<<' depending on current page and total page count. Same for last button
    first_btn = paginator_skip_to_start_label if start != 0 else str(1)
    last_btn = paginator_skip_to_end_label if end < total_pages else str(total_pages)
    labels = [first_btn] + [str(i + 1) for i in range(start + 1, end - 1)] + [last_btn]
    # As a last thing, add decoration for current page button
    labels[current_page - start] = '[' + str(labels[current_page - start]) + ']'
    return labels


def create_page_heading(total_pages: int, current_page: int) -> str:
    """ Creates page heading. Returns empty string, if only one page"""
    return f'[Sivu ({current_page + 1} / {total_pages})]\n'

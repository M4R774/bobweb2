from typing import List, Callable, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import CallbackContext

from bobweb.bob.activities.activity_state import ActivityState

# Buttons labels for paginator skip to start and skipt to end buttons
paginator_skip_to_start_label = '<<'
paginator_skip_to_end_label = '>>'

current_page_prefix_char = '['
current_page_postfix_char = ']'


class PaginatorState(ActivityState):
    """
    Generic activity state for any paginated content. Handles only pagination, content must be provided by caller.
    Content is lazy-loaded with given callable when page is changed. Indexes start from 0, labels start from 1.
    'markup_loader' is optional parameter for any callable that provides markup for the pages content.
    """
    def __init__(self, page_provider: Callable, page_count: int, current_page: int = 0, markup_provider: Callable = None):
        super().__init__()
        self.page_provider: Callable = page_provider
        self.markup_provider: Optional[Callable] = markup_provider
        self.page_count: int = page_count
        self.current_page: int = current_page

    def execute_state(self):
        if self.page_count > 1:
            pagination_labels = create_page_labels(self.page_count, self.current_page)
            buttons = [InlineKeyboardButton(text=label, callback_data=label) for label in pagination_labels]
        else:
            buttons = []
        # Calls page loader to load content for the given page
        additional_buttons = self.markup_provider() if self.markup_provider else []
        all_buttons = buttons + additional_buttons
        markup = InlineKeyboardMarkup(all_buttons) if len(all_buttons) > 0 else None

        page_content = self.page_provider(self.current_page)
        self.activity.reply_or_update_host_message(page_content, markup=markup, parse_mode=ParseMode.MARKDOWN_V2)

    def handle_response(self, response_data: str, context: CallbackContext = None):
        if response_data == paginator_skip_to_start_label:
            next_page = 0
        elif response_data == paginator_skip_to_end_label:
            next_page = self.page_count - 1
        else:
            next_page = int(response_data.replace(current_page_prefix_char, '')
                            .replace(current_page_postfix_char, '')) - 1
        self.current_page = next_page
        self.execute_state()


class ContentPaginatorState(PaginatorState):
    """
    Implementation of Paginator for paginating basic text content. Useful for when it is preferred to have content
    paginated. Adds heading to all pages by default.

    Note!
    - This adds additional heading with page number around the content for each page (heading). Page should contain
      at most 4076 characters which leaves 20 characters to the heading and few line breaks
    - As bots activities are stored in memory, each activity's state is lost in bots reset. So paginated messages
      non-visible content is no longer available after bot is restarted.

    Indexes start from 0, labels start from 1.
    """
    def __init__(self, pages: List[str], current_page: int = 0):
        self.pages = pages
        super().__init__(page_provider=self.page_loader, page_count=len(pages), current_page=current_page)

    def page_loader(self, index):
        """ Default implementation that adds heading to each page"""
        heading = create_page_heading(self.page_count, self.current_page) if self.page_count > 0 else ''
        return heading + self.pages[index]


def create_page_labels(total_pages: int, current_page: int, max_buttons: int = 7) -> List[str]:
    """ Creates buttons labels for simple paginator element. Check tests for examples. Works like standard paginator
        element where buttons are shown up to defined max_buttons count. Current page is surrounded '[x]'"""
    if total_pages == 1:
        return [f'{current_page_prefix_char}1{current_page_postfix_char}']

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
    labels[current_page - start] = current_page_prefix_char + str(labels[current_page - start]) + current_page_postfix_char
    return labels


def create_page_heading(total_pages: int, current_page: int) -> str:
    """ Creates page heading. Returns empty string, if only one page"""
    return f'[Sivu ({current_page + 1} / {total_pages})]\n'

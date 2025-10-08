import logging
import random

from aiohttp import ClientResponseError
from bs4 import BeautifulSoup
from django.utils import html
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from bot import async_http, utils_common
from bot.message_board import MessageWithPreview
from bot.resources.recipes import recipes
from bot.commands.base_command import BaseCommand, regex_simple_command_with_parameters
from telegram import Update

from bot.utils_common import MessageBuilder

logger = logging.getLogger(__name__)


def html_escape_if_not_none(text: str) -> str:
    return None if text is None else html.escape(text)


class RecipeDetails:
    """ Represents single recipe details fetched from external service. Some attributes are kept as string as
        there is no guarantee that recipe metadata exists and/or is in consistent parseable format """
    def __init__(self,
                 url: str,
                 metadata_fetched: bool,
                 name: str = None,
                 description: str = None,
                 servings: str = None,
                 prep_time: str = None,
                 difficulty: str = None):
        self.url: str = url
        self.metadata_fetched = metadata_fetched
        self.name: str = html_escape_if_not_none(name)
        self.description: str = html_escape_if_not_none(description)
        self.servings: int = int(servings) if servings and servings.isdigit() else None
        self.prep_time: str = html_escape_if_not_none(prep_time)
        self.difficulty: str = html_escape_if_not_none(difficulty)

    def to_message_with_html_parse_mode(self) -> str:
        if not self.metadata_fetched:
            return self.url

        # Message builder is used to avoid printing rows for content that is not available
        return (MessageBuilder()
                .append_to_new_line(self.name, '<b>', '</b>')
                .append_to_new_line(self.description, '<i>', '</i>')
                .append_raw('\n')
                .append_to_new_line(self.difficulty, '🎯 Vaikestaso: <b>', '</b>')
                .append_to_new_line(self.prep_time, '⏱ Valmistusaika: <b>', '</b>')
                .append_to_new_line(self.servings, '👨‍👩‍👧‍👦 Annoksia: <b>', '</b>')
                .append_to_new_line(self.url, '🔗 <a href="', '">linkki reseptiin (soppa 365)</a>')
                ).message.strip()


# Soppa 365 labels
servings_count_label = 'Annoksia'
preparation_time_label = 'Valmistusaika'
difficulty_label = 'Vaikeustaso'


class RuokaCommand(BaseCommand):
    def __init__(self):
        super().__init__(
            name='ruoka',
            regex=regex_simple_command_with_parameters('ruoka'),
            help_text_short=('!ruoka', 'Ruokaresepti')
        )

    def is_enabled_in(self, chat):
        return chat.ruoka_enabled

    async def handle_update(self, update: Update, context: CallbackContext = None):
        """
        Finds random receipt from ones listed in recipes.py, and scrapes metadata for the receipt from
        https://www.soppa365.fi receipt page, parses it and sends it to the user.
        """
        parameter = self.get_parameters(update.effective_message.text)

        recipes_with_parameter_text = [r for r in recipes if parameter in r.replace('-', ' ')]

        if len(recipes_with_parameter_text) > 0:
            recipe_url = random.choice(recipes_with_parameter_text)  # NOSONAR
        else:
            recipe_url = random.choice(recipes)  # NOSONAR

        # Fetch recipe details and form message
        recipe_details: RecipeDetails = await fetch_and_parse_recipe_details_from_soppa365(recipe_url)
        await update.effective_chat.send_message(recipe_details.to_message_with_html_parse_mode(),
                                                 parse_mode=ParseMode.HTML)


async def create_message_board_daily_message() -> MessageWithPreview:
    recipe_link = random.choice(recipes)  # NOSONAR
    recipe_details: RecipeDetails = await fetch_and_parse_recipe_details_from_soppa365(recipe_link)
    message = 'Päivän resepti: ' + recipe_details.to_message_with_html_parse_mode()
    return MessageWithPreview(message, None, ParseMode.HTML)


async def fetch_and_parse_recipe_details_from_soppa365(recipe_url: str) -> RecipeDetails:
    """
    Fetches and parses www.soppa365.fi recipe web page for given url. Html-response is parsed into virtual DOM,
    from which details of the recipe is searched with selectors. If web page get request fails, returns RecipeDetails
    with containing only the url and having 'metadata_fetched' == False.
    """
    try:
        html_content = await async_http.get_content_text(recipe_url)
        return parse_recipe_details(recipe_url, html_content)
    except (ClientResponseError, KeyError, AttributeError) as e:
        logger.error(f'Tried to fetch recipe web page for url: {recipe_url}. Error:\n{repr(e)}')
        return RecipeDetails(url=recipe_url, metadata_fetched=False)


def parse_recipe_details(recipe_url: str, html_content: str) -> RecipeDetails:
    # Parse html content to virtual DOM and search for the metadata
    html_dom = BeautifulSoup(html_content, 'html.parser')

    # Find recipe name
    h1_element = html_dom.find('h1')
    recipe_name = h1_element.find('a').text

    # Find first 'group-recipe-info' on the page. Single page response from Soppa 365 contains multiple recipes
    # where the requested recipe is first in the page.
    recipe_info_elements = html_dom.find_all('div', class_='group-recipe-info')
    recipe_info_div = recipe_info_elements[0]
    # Extract the next siblings 'div.field-items' text of each 'div.field-label'
    labels = recipe_info_div.find_all('div', class_='field-label')
    data = {}
    for label in labels:
        value_div = label.find_next_sibling('div', class_='field-items')
        if value_div:
            value = value_div.get_text(strip=True)
            data[label.get_text(strip=True)] = value

    # Print or use the values extracted, use the exact labels to access them
    servings = data[servings_count_label]
    prep_time = data[preparation_time_label]
    difficulty = data[difficulty_label]

    # Find description
    description_meta_tags = html_dom.find_all('meta', attrs={'name': 'description'})
    first_description_content = utils_common.object_search(description_meta_tags, 0, 'attrs', 'content')

    return RecipeDetails(
        url=recipe_url,
        metadata_fetched=True,
        name=recipe_name,
        description=first_description_content,
        servings=servings,
        prep_time=prep_time,
        difficulty=difficulty
    )

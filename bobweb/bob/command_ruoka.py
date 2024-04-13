import logging
import random

from aiohttp import ClientResponseError
from bs4 import BeautifulSoup
from telegram.ext import CallbackContext

from bobweb.bob import async_http, utils_common
from bobweb.bob.message_board import ScheduledMessage
from bobweb.bob.resources.recipes import recipes
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from telegram import Update


logger = logging.getLogger(__name__)


class RecipeDetails:
    """ Represents single recipe details fetched from external service. Some attributes are kept as string as
        there is no guarantee that recipe metadata exists and/or is in consistent parseable format """
    def __init__(self,
                 url: str,
                 metadata_fetched: bool,
                 name: str = None,
                 description: str = None,
                 servings: int = None,
                 prep_time: str = None,
                 difficulty: str = None):
        self.url: str = url
        self.metadata_fetched = metadata_fetched
        self.name: str = name
        self.description: str = description
        self.servings: int = servings
        self.prep_time: str = prep_time
        self.difficulty: str = difficulty


# Soppa 365 labels
servings_count_label = 'Annoksia'
preparation_time_label = 'Valmistusaika'
difficulty_label = 'Vaikeustaso'


class RuokaCommand(ChatCommand):
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
        Send a message when the command /ruoka is issued.
        Returns link to page in https://www.soppa365.fi
        """
        # TODO: REMOVE THIS OVERRIDE
        await create_message_board_daily_message()
        return


        parameter = self.get_parameters(update.effective_message.text)

        recipes_with_parameter_text = [r for r in recipes if parameter in r.replace('-', ' ')]

        if len(recipes_with_parameter_text) > 0:
            reply_text = random.choice(recipes_with_parameter_text)  # NOSONAR
        else:
            reply_text = random.choice(recipes)  # NOSONAR

        await update.effective_chat.send_message(reply_text)


async def create_message_board_daily_message(chat_id: int = None) -> ScheduledMessage:
    recipe_link = random.choice(recipes)  # NOSONAR
    # Find name link by extracting last part of link after '/' and replacing dashes with spaces
    recipe_details: RecipeDetails = await fetch_and_parse_recipe_details_from_soppa365(recipe_link)


async def fetch_and_parse_recipe_details_from_soppa365(recipe_url: str) -> RecipeDetails:
    """
    Fetches and parses www.soppa365.fi recipe web page for given url. Html-response is parsed into virtual DOM,
    from which details of the recipe is searched with selectors. If web page get request fails, returns RecipeDetails
    with containing only the url and having 'metadata_fetched' == False.
    """
    try:
        html_content = await async_http.fetch_content_text(recipe_url)
        recipe_details: RecipeDetails = parse_recipe_details(recipe_url, html_content)
    except ClientResponseError as e:
        logger.error(f'Tried to fetch recipe web page for url: {recipe_url}. Error:\n{repr(e)}')
        return RecipeDetails(url=recipe_url, metadata_fetched=False)

    print(f"Servings: {recipe_details.servings}, "
          f"Prep time: {recipe_details.prep_time}, "
          f"Difficulty: {recipe_details.difficulty}, "
          f"Description: {recipe_details.description}")


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

# EXAMPLE
#
# <div class="group-recipe-info">
#     <div
#         class="field field-name-field-recipe-servings-text field-type-text field-label-inline clearfix view-mode-full">
#         <div class="field-label">Annoksia</div>
#         <div class="field-items">
#             <div class="field-item even">4</div>
#         </div>
#     </div>
#     <div
#         class="field field-name-field-recipe-cooking-time-text field-type-text field-label-inline clearfix view-mode-full">
#         <div class="field-label">Valmistusaika</div>
#         <div class="field-items">
#             <div class="field-item even">30 min</div>
#         </div>
#     </div>
#     <div
#         class="field field-name-field-recipe-difficulty field-type-list-integer field-label-inline clearfix view-mode-full">
#         <div class="field-label">Vaikeustaso</div>
#         <div class="field-items">
#             <div class="field-item even">Helppo</div>
#         </div>
#     </div>
# </div>
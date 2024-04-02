import random

from bs4 import BeautifulSoup
from telegram.ext import CallbackContext

from bobweb.bob import async_http
from bobweb.bob.message_board import ScheduledMessage
from bobweb.bob.resources.recipes import recipes
from bobweb.bob.command import ChatCommand, regex_simple_command_with_parameters
from telegram import Update


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
    html_content = await async_http.fetch_content_text(recipe_link)
    html_dom = BeautifulSoup(html_content, 'html.parser')

    # Find first 'group-recipe-info' on the page
    recipe_info_div = html_dom.find_all('div', class_='group-recipe-info')[0]
    # Extract the next siblings 'div.field-items' text of each 'div.field-label'
    labels = recipe_info_div.find_all('div', class_='field-label')
    data = {}
    for label in labels:
        value_div = label.find_next_sibling('div', class_='field-items')
        if value_div:
            value = value_div.get_text(strip=True)
            data[label.get_text(strip=True)] = value

    # Print or use the values extracted, use the exact labels to access them
    servings = data['Annoksia']
    prep_time = data['Valmistusaika']
    difficulty = data['Vaikeustaso']

    # Find description
    description_meta_tags = html_dom.find_all('meta', attrs={'name': 'description'})[0]
    first_description_content = description_meta_tags['content']

    print(f"Servings: {servings}, Prep time: {prep_time}, Difficulty: {difficulty}, Description: {first_description_content}")

    # recipe_name = recipe_link.split('/')[-1].replace('-', ' ')
    # Try to find additional details of the recipe

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
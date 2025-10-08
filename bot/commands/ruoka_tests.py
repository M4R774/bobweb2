from unittest import mock
from django.test import TransactionTestCase
from bot.commands.ruoka import RuokaCommand, RecipeDetails
from bot.resources.recipes import recipes
from bot.tests_utils import assert_reply_to_contain, assert_get_parameters_returns_expected_value, \
    assert_command_triggers, async_raise_client_response_error

ASYNC_HTTP_GET_TEXT = 'bot.async_http.get_content_text'
RUOKA_COMMAND = '/ruoka'
FIRST_RECIPE_URL = recipes[0]


def get_content_text_mock(return_value: str):
    async def get_content_text(_: str):  #NOSONAR (S7503)
        return return_value
    return get_content_text

with open('bot/resources/test/soppa_365_example_receipt_snippet.html') as snippet:
    soppa_365_example_receipt_snippet = snippet.read()

@mock.patch('random.choice', lambda values: values[0])
@mock.patch(ASYNC_HTTP_GET_TEXT, get_content_text_mock(soppa_365_example_receipt_snippet))
class RuokaCommandTest(TransactionTestCase):
    async def test_command_triggers(self):
        should_trigger = ['/ruoka', '!ruoka', '.ruoka', '/RUOKA', '/ruoka test']
        should_not_trigger = ['ruoka', 'test /ruoka', ]
        await assert_command_triggers(self, RuokaCommand, should_trigger, should_not_trigger)

    async def test_get_given_parameter(self):
        assert_get_parameters_returns_expected_value(self, '!ruoka', RuokaCommand())

    async def test_should_return_a_link(self):
        await assert_reply_to_contain(self, '.ruoka', [FIRST_RECIPE_URL])

    async def test_should_return_item_with_given_prompt_in_link(self):
        await assert_reply_to_contain(self, '!ruoka mozzarella', ['mozzarella-gnocchivuoka'])

    async def test_should_return_random_item_if_no_recipe_link_contains_prompt(self):
        with mock.patch('random.choice', lambda values: values[2]):
            await assert_reply_to_contain(self, '/ruoka asdasdasdasdasd', ['kookos-linssikeitto'])


@mock.patch('random.choice', lambda values: values[0])
class RuokaCommandErrorTests(TransactionTestCase):

    @mock.patch(ASYNC_HTTP_GET_TEXT, async_raise_client_response_error(status=500))
    async def test_handles_network_error(self):
        await assert_reply_to_contain(self, RUOKA_COMMAND, [FIRST_RECIPE_URL])

    @mock.patch(ASYNC_HTTP_GET_TEXT)
    async def test_handles_malformed_data(self, mock_get_content_text):
        mock_get_content_text.return_value = "<html><body>Invalid Data</body></html>"
        await assert_reply_to_contain(self, RUOKA_COMMAND, [FIRST_RECIPE_URL])

    def test_recipe_details_with_missing_metadata(self):
        details = RecipeDetails(url="http://example.com", metadata_fetched=True, name=None, description=None)
        message = details.to_message_with_html_parse_mode()
        self.assertEquals("🔗 <a href=\"http://example.com\">linkki reseptiin (soppa 365)</a>", message)


    def test_recipe_details_formatting(self):
        details = RecipeDetails(
            url="http://example.com",
            metadata_fetched=True,
            name="Test Recipe",
            description="Delicious meal",
            servings="4",
            prep_time="30 minutes",
            difficulty="Easy"
        )

        message = details.to_message_with_html_parse_mode()
        self.assertEqual(expected_message.strip(), message)


expected_message = \
'''
<b>Test Recipe</b>
<i>Delicious meal</i>

🎯 Vaikestaso: <b>Easy</b>
⏱ Valmistusaika: <b>30 minutes</b>
👨‍👩‍👧‍👦 Annoksia: <b>4</b>
🔗 <a href="http://example.com">linkki reseptiin (soppa 365)</a>
'''

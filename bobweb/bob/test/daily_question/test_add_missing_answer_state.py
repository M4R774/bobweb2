import os

import django
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory

from bobweb.bob import main  # needed to not cause circular import
from django.test import TestCase

from bobweb.bob.activities.daily_question.add_missing_answer_state import message_saved_no_answer_to_last_dq, \
    new_answer_btn, answer_without_message_saved

from bobweb.bob.test.daily_question.utils import populate_season_with_dq_and_answer_v2, populate_season_v2, \
    populate_questions_with_answers_v2
from bobweb.bob.tests_mocks_v2 import init_chat_user, MockUser, MockChat
from bobweb.bob.tests_msg_btn_utils import assert_buttons_equal_to_reply_markup
from bobweb.web.bobapp.models import DailyQuestionAnswer


@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
class AddWinningAnswerWithoutMessageTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(AddWinningAnswerWithoutMessageTests, cls).setUpClass()
        django.setup()
        os.system("python ../web/manage.py migrate")

    def test_when_winner_has_no_answer_to_prev_dq_message_contains_info_and_btn(self, chat: MockChat = None, user: MockUser = None):
        chat = chat or MockChat()
        # Call populator that creates new dq and answer by new users
        populate_season_with_dq_and_answer_v2(chat)

        # Now with the user that has not yet answered previous daily question, trigger new daily question
        user_without_answer = user or MockUser(chat=chat)
        user.send_message('asd')
        user_without_answer.send_message('#päivänkysymys this should trigger MarkAnswerOrSaveAnswerWithoutMessage')

        self.assertEqual(message_saved_no_answer_to_last_dq, chat.last_bot_txt())
        expected_buttons = [new_answer_btn]
        assert_buttons_equal_to_reply_markup(self, expected_buttons, chat.last_bot_msg().reply_markup)

    def test_when_add_new_answer_button_is_clicked_new_answer_is_added(self, chat: MockChat = None, user: MockUser = None):
        # Use previous test case as populator for this
        chat = chat or MockChat()
        user = user or MockUser(chat=chat)
        self.test_when_winner_has_no_answer_to_prev_dq_message_contains_info_and_btn(chat, user)

        initial_answer_count = DailyQuestionAnswer.objects.count()

        # Press button to add new winning answer without message
        user.press_button(new_answer_btn)

        # Now one more answer should be saved to the database
        answers = list(DailyQuestionAnswer.objects.all())
        self.assertEqual(initial_answer_count + 1, len(answers))

        # New answer should have no content and be marked as winning
        new_answer = answers[-1]
        self.assertTrue(new_answer.is_winning_answer)
        self.assertIsNone(new_answer.content)

        # Bot should have edited message to contain notification and buttons should be removed
        self.assertEqual(answer_without_message_saved, chat.last_bot_txt())
        assert_buttons_equal_to_reply_markup(self, [], chat.last_bot_msg().reply_markup)

    @freeze_time('2023-01-02', as_kwarg='clock')
    def test_add_new_answer_works_even_when_multiple_dq_in_database(self, clock: FrozenDateTimeFactory):
        # Init chat and call populator three times to add new questions to database
        chat = MockChat()
        populate_season_v2(chat)
        populate_questions_with_answers_v2(chat, 3, clock)

        # Now test that previous test works as expected in the same chat context
        self.test_when_add_new_answer_button_is_clicked_new_answer_is_added(chat)

    def test_informs_if_new_winning_answer_has_been_added_after_last_error(self):
        # In theory, user could first mark their answer with '/vastaus' command and
        # after that try to add wining answer without message as well. This test confirms
        # that if user gets the no-message-error, marks their answer and after that presses
        # the button, no extra answers are added

        # Use previous test case as populator for this
        chat, user = init_chat_user()
        self.test_when_winner_has_no_answer_to_prev_dq_message_contains_info_and_btn(chat, user)

        initial_answer_count = DailyQuestionAnswer.objects.count()

        users_first_msg = user.messages[0]
        # Now user marks their first msg as winning one and it is expected to work
        user.send_message('/vastaus', reply_to_message=users_first_msg)
        self.assertIn('Kohdeviesti tallennettu onnistuneesti voittaneena vastauksena sitä '
                      'edeltäneeseen päivän kysymykseen', chat.last_bot_txt())

        answers = list(DailyQuestionAnswer.objects.all())
        self.assertEqual(initial_answer_count + 1, len(answers))
        self.assertTrue(answers[-1].is_winning_answer)  # Last answer should be winning one

        # Now user tries to press the button as well. Bots message with the button is second from the last
        user.press_button(new_answer_btn, msg_with_btns=chat.bot.messages[-2])

        # Bot should give message, that the winner has already been set
        self.assertIn('Päivän kysymys on saanut välissä voittaneen vastauksen. Uutta viestitöntä '
                      'voittanutta vastausta ei tallennetu.', chat.last_bot_txt())

        # There should still be only 1 more answer after the initial answer count
        answers = list(DailyQuestionAnswer.objects.all())
        self.assertEqual(initial_answer_count + 1, len(answers))

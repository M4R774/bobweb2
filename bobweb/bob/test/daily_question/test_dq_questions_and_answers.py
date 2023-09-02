import datetime
import os
from bobweb.bob import main

import django
from django.test import TestCase
from freezegun import freeze_time

from bobweb.bob.activities.daily_question.daily_question_errors import LastQuestionWinnerAlreadySet, \
    NoAnswerFoundToPrevQuestion
from bobweb.bob.activities.daily_question.message_utils import dq_created_from_msg_edit
from bobweb.bob.command_daily_question import DailyQuestionHandler
from bobweb.bob.test.daily_question.utils import populate_season_v2, populate_season_with_dq_and_answer_v2
from bobweb.bob.tests_mocks_v2 import MockMessage, MockChat, init_chat_user, MockUser
from bobweb.bob.tests_utils import assert_command_triggers
from bobweb.web.bobapp.models import DailyQuestion, DailyQuestionAnswer


@freeze_time('2023-01-02', tick=True)  # Set default time to first monday of 2023 as business logic depends on the date
class DailyQuestionTestSuiteV2(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(DailyQuestionTestSuiteV2, cls).setUpClass()
        django.setup()
        management.call_command('migrate')

    def test_command_triggers(self):
        should_trigger = ['#päivänkysymys', 'asd\nasd #päivänkysymys', '#päivänkysymys asd\nasd',
                          'asd\nasd #päivänkysymys asd\nasd ', '#PÄIVÄNKYSYMYS ???']
        should_not_trigger = ['päivänkysymys', '/päivänkysymys', '/päivänkys', '# päivänkys', '#paivankysymys']
        await assert_command_triggers(self, DailyQuestionHandler, should_trigger, should_not_trigger)

    #
    # Daily Questions
    #

    def test_when_chat_has_season_question_is_saved_v2(self):
        chat, user = init_chat_user()
        populate_season_v2(chat)
        await user.send_message("#päivänkysymys kuka?")

        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)

    def test_reply_to_daily_question_is_saved_as_answer_v2(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        dq = DailyQuestion.objects.order_by('-id').first()

        mock_dq_msg = MockMessage(text='#päivänkysymys', chat=chat, from_user=dq.question_author, message_id=dq.message_id)
        await user.send_message('a2', reply_to_message=mock_dq_msg)

        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertEqual(1, len(answers))
        self.assertEqual('a2', answers[0].content)

    def test_edit_to_answer_updates_its_content_v2(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        dq = DailyQuestion.objects.order_by('-id').first()

        # send answer that is reply to mocked dq message
        mock_dq_msg = MockMessage(text='#päivänkysymys', chat=chat, from_user=dq.question_author, message_id=dq.message_id)

        await answer = user.send_message('a', reply_to_message=mock_dq_msg)

        # edit previous message. After this should be updated in the database
        answer.edit_message('a (edited)')

        answers = list(DailyQuestionAnswer.objects.filter(answer_author__id=user.id))
        self.assertEqual(1, len(answers))
        self.assertEqual('a (edited)', answers[0].content)

    def test_when_question_is_saved_its_sender_is_set_as_prev_question_winner_v2(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)

        # Check that no answer is marked as winning one
        winning_answers = list(DailyQuestionAnswer.objects.filter(is_winning_answer=True))
        self.assertEqual(0, len(winning_answers))

        # get prepopulated user, that has answered prepopulated dq in populate method (last new user in chat)
        user = chat.users[-1]
        await user.send_message("#päivänkysymys kuka?")

        # Check that user's reply to the daily question has been marked as winning one
        winning_answers = list(DailyQuestionAnswer.objects.filter(is_winning_answer=True))
        self.assertEqual(1, len(winning_answers))
        self.assertEqual(user.id, winning_answers[-1].answer_author.id)

    def test_editing_hashtag_to_message_creates_new_daily_question_v2(self):
        chat, user = init_chat_user()
        populate_season_v2(chat)
        await message = user.send_message("kuka?")
        message.edit_message("#päivänkysymys kuka?")

        self.assertEqual(dq_created_from_msg_edit(False), chat.bot.messages[-1].text)

        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys kuka?', daily_questions[0].content)

    def test_editing_saved_daily_question_updates_saved_content_v2(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)
        dq = DailyQuestion.objects.filter().first()
        self.assertEqual('#päivänkysymys dq1', dq.content)

        # send answer that is reply to mocked dq message
        mock_dq_msg = MockMessage(chat, from_user=dq.question_author, message_id=dq.message_id)
        mock_dq_msg.edit_message("#päivänkysymys (edited)")
        daily_questions = list(DailyQuestion.objects.all())
        self.assertEqual(1, len(daily_questions))
        self.assertEqual('#päivänkysymys (edited)', daily_questions[0].content)

    @freeze_time('2023-01-02', as_kwarg='clock')
    def test_same_user_sending_dq_as_last_one_gives_error_v2(self, clock):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)

        clock.tick(datetime.timedelta(days=1))  # Move test logic time one day forward
        user = chat.users[1]
        await user.send_message("#päivänkysymys dq2")

        expected_reply = 'Päivän kysyjä on sama kuin aktiivisen kauden edellisessä kysymyksessä. ' \
                         'Kysymystä ei tallennetu.'
        self.assertEqual(expected_reply, chat.bot.messages[-1].text)

    @freeze_time('2023-01-02', as_kwarg='clock')
    def test_date_of_question_confirmation_v2(self, clock):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        dq_msg = chat.messages[-4]  # prepopulated daily question message
        print(dq_msg.text)
        await user.send_message("vastaus", reply_to_message=dq_msg)

        # Move 2 days forward so there is a gap between current date and last date of question
        clock.tick(datetime.timedelta(days=2))
        await user.send_message("#päivänkysymys dq2")

        # Test invalid date and date that is before last question
        self.assertIn('vahvistatko vielä minkä päivän päivän kysymys on kyseessä', chat.last_bot_txt())
        user.reply_to_bot('tiistai')
        self.assertIn('Antamasi päivämäärä ei ole tuettua muotoa', chat.last_bot_txt())
        user.reply_to_bot('01.01.1999')
        self.assertIn('Päivämäärä voi olla aikaisintaan edellistä kysymystä seuraava päivä', chat.last_bot_txt())

        # End context manager, as now we want to get given date from datetime.fromisoformat-call
        user.reply_to_bot('03.01.2023')
        self.assertIn('Kysymyksen päiväksi vahvistettu 03.01.2023', chat.last_bot_txt())

        # Now last dq should have given date of question
        dq = DailyQuestion.objects.last()
        self.assertIn('2023-01-03', str(dq.date_of_question))

    def test_using_dq_hashtag_second_time_in_same_day_does_nothing(self):
        chat, user = init_chat_user()
        populate_season_v2(chat)
        await user.send_message('#päivänkysymys mikä?')
        self.assertEqual(1, DailyQuestion.objects.count())

        message_count = len(chat.messages)
        # Now user sends another message with same tag
        await user.send_message('#päivänkysymys tulosten aika!')
        self.assertEqual(1, DailyQuestion.objects.count())  # No new dq
        self.assertEqual(message_count + 1, len(chat.messages))  # No other new messages, than what user sent

    def test_no_more_than_one_dq_per_date_is_saved(self):
        chat = MockChat()
        populate_season_with_dq_and_answer_v2(chat)

        user1 = chat.users[1]  # User who has presented 1 daily question
        user2 = chat.users[2]  # User who has answered 1 answer to the presented dq
        await user2.send_message('#päivänkysymys this is next day question')
        self.assertEqual(2, DailyQuestion.objects.count())

        last_dq = DailyQuestion.objects.last()
        self.assertIn('2023-01-03', str(last_dq.date_of_question))

        # Now user 1 tries to send third dq-message on the same day. Now as current day's and next day's question is
        # already set, should prevent from adding new question
        await user1.send_message('#päivänkysymys should not be persisted')
        expected_reply = 'Päivämäärälle 03.01.2023 on jo tallennettu päivän kysymys.'
        self.assertIn(expected_reply, chat.last_bot_txt())
        self.assertEqual(2, DailyQuestion.objects.count())

    def test_gives_instructions_to_mark_answer_when_saving_winner_if_author_has_no_answer_to_last_dq(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        await user.send_message('users answer, but not reply to dq, so not saved as answer')

        # user has not answered prepopulated daily question. Should give error when trying to set winner
        await user.send_message('#päivänkysymys should notify author not set winner as no answer to last dq')
        self.assertIn(NoAnswerFoundToPrevQuestion.localized_msg, chat.bot.messages[-1].text)
        assert_there_are_no_winning_answers(self)

    # This should not be able to happend at all, but let's test for it anyway
    def test_gives_error_when_saving_winner_if_winner_already_set(self):
        chat, user = init_chat_user()
        populate_season_with_dq_and_answer_v2(chat)
        answer = DailyQuestionAnswer.objects.first()
        answer.is_winning_answer = True
        answer.save()

        # now as last questions only answer is set as winning one somehow, should give error, that winner cannot be set
        user = chat.users[-1]  # User who sent the answer
        await user.send_message('#päivänkysymys this should be saved without problem')

        expected_reply = LastQuestionWinnerAlreadySet.localized_msg
        self.assertIn(expected_reply, chat.bot.messages[-1].text)


def assert_there_are_no_winning_answers(case: TestCase):
    answers = DailyQuestionAnswer.objects.filter(is_winning_answer=True)
    case.assertEqual(0, answers.count())

from django.db import models
from django.db.models import Q, UniqueConstraint


class DailyQuestion(models.Model):
    id = models.IntegerField(primary_key=True)
    season = models.ForeignKey('DailyQuestionSeason', on_delete=models.CASCADE, null=False)  # Ei voi olla ilman seasonia
    datetime = models.DateTimeField(null=False)
    update_id = models.IntegerField(null=False)
    update_author = models.ForeignKey('TelegramUser', null=False, on_delete=models.CASCADE,
                                      related_name='daily_questions')
    content = models.CharField(max_length=4096, null=False)

    class Meta:
        db_table = 'bobapp_daily_question'
        unique_together = ("datetime", "season")

    def __str__(self):
        return "kysymys_pvm_" + self.datetime.__str__()
    objects = models.Manager()


# Tämä vain ajatusta herättämässä
class DailyQuestionAnswer(models.Model):
    id = models.IntegerField(primary_key=True)
    question = models.ForeignKey('DailyQuestion', on_delete=models.CASCADE, null=False)
    datetime = models.DateTimeField(null=False)
    update_id = models.IntegerField(null=False)
    update_author = models.ForeignKey('TelegramUser', null=False, on_delete=models.CASCADE,
                                      related_name='daily_question_answers')
    content = models.CharField(max_length=4096, null=False)
    is_winning_answer = models.BooleanField(null=False, default=False)

    class Meta:
        db_table = 'bobapp_daily_question_answer'
        unique_together = ('question', 'update_author')
        # Makes sure, that only one answer per question can be marked as winning answer
        constraints = [
            UniqueConstraint(fields=['question', 'is_winning_answer'],
                             condition=Q(is_winning_answer=True),
                             name='unique_is_winning_answer')
        ]

    objects = models.Manager()


# Chat kohtainen season kysymyksille
class DailyQuestionSeason(models.Model):
    id = models.IntegerField(primary_key=True)
    chat = models.ForeignKey('Chat', null=False, on_delete=models.CASCADE)
    season_number = models.IntegerField(null=False)  # Voisi olla mahdollista antaa myös nimi tms
    start_datetime = models.DateTimeField(null=False)  # HUOM! Ei päälekkäisiä kausia
    end_datetime = models.DateTimeField(null=True)

    class Meta:
        db_table = 'bobapp_daily_question_season'
        unique_together = ("id", "chat", "season_number", "start_datetime", "end_datetime")
    objects = models.Manager()


class Bob(models.Model):
    id = models.IntegerField(primary_key=True)
    uptime_started_date = models.DateTimeField(null=True)
    latest_startup_broadcast_message = models.TextField(null=True)
    global_admin = models.ForeignKey('TelegramUser', on_delete=models.CASCADE, null=True)


class TelegramUser(models.Model):
    id = models.IntegerField(primary_key=True)
    username = models.CharField(max_length=255, null=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    latest_promotion_from_git_commit = models.DateField(null=True)

    def __str__(self):
        if self.username is not None:
            return str(self.username)
        elif self.last_name is not None:
            return str(self.last_name)
        elif self.first_name is not None:
            return str(self.first_name)
        else:
            return str(self.id)
    objects = models.Manager()


# One telegram user might have several git aliases
class GitUser(models.Model):
    tg_user = models.ForeignKey('TelegramUser', on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=255, null=False, default=None)
    email = models.CharField(max_length=255, null=False, default=None)

    def __str__(self):
        return str(self.email)

    class Meta:
        unique_together = ("name", "email")
    objects = models.Manager()


class Chat(models.Model):
    id = models.IntegerField(primary_key=True)
    title = models.CharField(max_length=255, null=True)
    latest_leet = models.DateField(null=True)
    members = models.ManyToManyField(
        TelegramUser,
        through='ChatMember',
        through_fields=('chat', 'tg_user'),
    )

    leet_enabled = models.BooleanField(default=True)
    ruoka_enabled = models.BooleanField(default=True)
    space_enabled = models.BooleanField(default=True)
    broadcast_enabled = models.BooleanField(default=True)
    proverb_enabled = models.BooleanField(default=True)
    time_enabled = models.BooleanField(default=True)
    weather_enabled = models.BooleanField(default=True)
    or_enabled = models.BooleanField(default=True)
    huutista_enabled = models.BooleanField(default=True)

    def __str__(self):
        if self.title is not None and self.title != "":
            return str(self.title)
        elif int(str(self.id)) > 0:  # TODO: jotain robustimpaa tähän
            return str(TelegramUser.objects.get(id=self.id))
    objects = models.Manager()


# Chat members tie the users and chats. TelegramUser can be in many chats with different ranks.
class ChatMember(models.Model):
    chat = models.ForeignKey('Chat', null=False, on_delete=models.CASCADE)
    tg_user = models.ForeignKey('TelegramUser', null=False, on_delete=models.CASCADE)
    rank = models.PositiveIntegerField(default=0)
    prestige = models.PositiveIntegerField(default=0)
    message_count = models.PositiveIntegerField(default=0)
    admin = models.BooleanField(default=False)
    latest_weather_city = models.CharField(max_length=255, null=True)

    class Meta:
        unique_together = ("chat", "tg_user")
        ordering = ["-rank", "-prestige"]

    def __str__(self):
        return str(self.tg_user) + "@" + str(self.chat)
    objects = models.Manager()


# Viisaus
class Proverb(models.Model):
    proverb = models.TextField(unique=True)
    author = models.CharField(max_length=255, null=True)
    date_created = models.DateField(null=True)

    def __str__(self):
        return str(self.proverb)
    objects = models.Manager()


class ChatProverb(models.Model):
    chat = models.ForeignKey('Chat', null=False, on_delete=models.CASCADE)
    proverb = models.ForeignKey('Proverb', null=False, on_delete=models.CASCADE)
    number_of_appearances = models.PositiveIntegerField(default=0)
    last_appeared = models.DateTimeField(null=True)

    class Meta:
        unique_together = ("chat", "proverb")
        ordering = ["last_appeared"]

    def __str__(self):
        return str(self.proverb)
    objects = models.Manager()


class Reminder(models.Model):
    remember_this = models.TextField(unique=False)  # What to remind
    chat = models.ForeignKey("Chat", null=False, on_delete=models.CASCADE)  # Where to remind
    date_when_reminded = models.DateTimeField(null=False)  # When to remind

    class Meta:
        ordering = ["date_when_reminded"]

    def __str__(self):
        return str(self.remember_this)
    objects = models.Manager()

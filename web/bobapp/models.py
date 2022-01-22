from django.db import models


class TelegramUser(models.Model):
    id = models.IntegerField(primary_key=True)
    username = models.CharField(max_length=255, null=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)

    def __str__(self):
        if self.username is not None:
            return str(self.username)
        elif self.last_name is not None:
            return str(self.last_name)
        elif self.first_name is not None:
            return str(self.first_name)
        else:
            return str(self.id)


class Chat(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=255, null=True)
    latest_leet = models.DateField(null=True)
    members = models.ManyToManyField(
        TelegramUser,
        through='ChatMember',
        through_fields=('chat', 'tg_user'),
    )

    # feature_x_enabled = models.BooleanField(default=False)

    def __str__(self):
        return str(self.id)


# Chat members tie the users and chats. TelegramUser can be in many chats with different ranks.
class ChatMember(models.Model):
    chat = models.ForeignKey('Chat', null=False, on_delete=models.CASCADE)
    tg_user = models.ForeignKey('TelegramUser', null=False, on_delete=models.CASCADE)
    rank = models.PositiveIntegerField(default=0)
    prestige = models.PositiveIntegerField(default=0)
    message_count = models.PositiveIntegerField(default=0)
    admin = models.BooleanField(default=False)

    class Meta:
        unique_together = ("chat", "tg_user")
        ordering = ["-rank", "-prestige"]

    def __str__(self):
        return str(self.tg_user)


# Viisaus
class Proverb(models.Model):
    proverb = models.TextField(unique=True)
    author = models.CharField(max_length=255, null=True)
    date_created = models.DateField(null=True)

    def __str__(self):
        return str(self.proverb)


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


class Reminder(models.Model):
    remember_this = models.TextField(unique=False)  # What to remind
    chat = models.ForeignKey("Chat", null=False, on_delete=models.CASCADE)  # Where to remind
    date_when_reminded = models.DateTimeField(null=False)  # When to remind

    class Meta:
        ordering = ["date_when_reminded"]

    def __str__(self):
        return str(self.remember_this)

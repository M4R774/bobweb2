# Generated by Django 4.0.7 on 2023-01-28 17:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bobapp', '0018_dailyquestion_dailyquestionseason_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='chat',
            name='free_game_offers_enabled',
            field=models.BooleanField(default=False),
        ),
    ]

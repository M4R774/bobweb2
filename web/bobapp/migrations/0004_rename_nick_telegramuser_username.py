# Generated by Django 4.0.1 on 2022-01-21 21:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bobapp', '0003_remove_chat_message_count_chatmember_message_count'),
    ]

    operations = [
        migrations.RenameField(
            model_name='telegramuser',
            old_name='nick',
            new_name='username',
        ),
    ]

# Generated by Django 4.1.13 on 2024-11-18 17:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bobapp', '0031_chat_message_board_msg_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dailyquestionanswer',
            name='content',
            field=models.CharField(max_length=4096, null=True),
        ),
        migrations.AlterField(
            model_name='dailyquestionanswer',
            name='message_id',
            field=models.IntegerField(null=True),
        ),
    ]

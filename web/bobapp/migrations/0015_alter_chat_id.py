# Generated by Django 4.0.1 on 2022-02-06 09:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bobapp', '0014_chat_leet_enabled_chat_proverb_enabled_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chat',
            name='id',
            field=models.IntegerField(primary_key=True, serialize=False),
        ),
    ]

# Generated by Django 4.1.6 on 2023-03-20 12:41

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bobapp', '0021_chat_nordpool_graph_width'),
    ]

    operations = [
        migrations.AddField(
            model_name='bob',
            name='gpt_credit_card_holder',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='credit_card_holder', to='bobapp.telegramuser'),
        ),
        migrations.AddField(
            model_name='bob',
            name='gpt_system_message',
            field=models.TextField(default='You are a helpful Telegram chatbot called Bob. Answer questions as briefly as possible. You will be provided short snippet of the conversation so far. Messages starting with .gpt are addressed directly to you. Answer the latest message. '),
        ),
    ]
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bobapp', '0032_alter_dailyquestionanswer_message_id'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Bob',
            new_name='Bot',
        ),
        migrations.AlterModelTable(
            name='bot',
            table='bobapp_bot',
        ),
    ]


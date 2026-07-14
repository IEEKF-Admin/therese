from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0022_purchase_order_quote'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskcomment',
            name='entry_type',
            field=models.CharField(
                choices=[
                    ('created', 'Created'),
                    ('edited', 'Edited'),
                    ('user_message', 'User message'),
                ],
                default='user_message',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='taskcomment',
            name='text',
            field=models.TextField(blank=True),
        ),
        migrations.RemoveField(
            model_name='task',
            name='comment',
        ),
    ]
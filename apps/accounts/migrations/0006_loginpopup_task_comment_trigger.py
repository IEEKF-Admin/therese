from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_loginpopupconfig_audience_match_mode'),
    ]

    operations = [
        migrations.AlterField(
            model_name='loginpopupconfig',
            name='trigger',
            field=models.CharField(
                choices=[
                    ('first_login', 'First login (welcome / profile completion)'),
                    ('contract_ending_soon', 'Own contract ending in X months'),
                    ('any_contract_ending_soon', 'Any employee contract ending in X months'),
                    ('new_task_assigned', 'New task assigned to the user'),
                    ('task_status_changed', 'Status changed on a task created by the user'),
                    (
                        'task_comment_on_created_task',
                        'New message on a task created by the user (by someone else)',
                    ),
                    ('login_after_datetime', 'Login after specific date/time'),
                ],
                max_length=50,
            ),
        ),
    ]
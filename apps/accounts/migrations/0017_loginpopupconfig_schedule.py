from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_accountemailtemplate_attachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='loginpopupconfig',
            name='schedule_time',
            field=models.TimeField(
                blank=True,
                help_text='Local time of day for the recurring schedule trigger.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='loginpopupconfig',
            name='schedule_weekdays',
            field=models.CharField(
                blank=True,
                help_text='Comma-separated weekdays for the recurring schedule (0=Monday … 6=Sunday).',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='loginpopupconfig',
            name='trigger',
            field=models.CharField(
                choices=[
                    ('first_login', 'First login (welcome / profile completion)'),
                    ('contract_ending_soon', 'Own contract ending in X months'),
                    ('any_contract_ending_soon', 'Any employee contract ending in X months'),
                    ('new_task_assigned', 'New task assigned to the user'),
                    ('purchase_order_created', 'New purchase order (procurement) created'),
                    ('personnel_task_created', 'New personnel task created'),
                    ('task_status_changed', 'Status changed on a task created by the user'),
                    (
                        'task_comment_on_created_task',
                        'New message on a task created by the user (by someone else)',
                    ),
                    ('login_after_datetime', 'Login after specific date/time'),
                    ('scheduled', 'Recurring schedule (time and weekdays)'),
                    ('checklist_assigned', 'New checklist assigned to the user'),
                    (
                        'chemical_item_incomplete',
                        'Chemicals: own chemical item missing required inventory data',
                    ),
                    (
                        'chemical_item_delivered',
                        'Chemicals: own chemical item was delivered (complete inventory data)',
                    ),
                    ('holiday_request_submitted', 'Holiday request submitted (for approvers)'),
                    ('holiday_request_approved', 'Own holiday request was approved'),
                    ('holiday_request_rejected', 'Own holiday request was rejected'),
                    ('holiday_request_deleted', 'Holiday request deleted'),
                ],
                max_length=50,
            ),
        ),
    ]

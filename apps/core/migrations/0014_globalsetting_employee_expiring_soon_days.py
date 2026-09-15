from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_holidays_module_switch'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsetting',
            name='employee_expiring_soon_days',
            field=models.PositiveIntegerField(
                default=90,
                help_text=(
                    'Employees whose current contract ends within this many days '
                    '(and who have no seamless follow-up) match the Expiring soon filter '
                    'on the employee list.'
                ),
                verbose_name='Employee “Expiring soon” window (days)',
            ),
        ),
    ]

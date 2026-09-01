from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0028_contract_weekly_hours_3dp'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='is_external',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Person is not an institute employee. Shown in the employee list '
                    'with an External badge. No phone list, holidays, or cost reports. '
                    'Employee number is optional. Link an existing Django user for login '
                    'and group permissions.'
                ),
                verbose_name='External',
            ),
        ),
        migrations.AlterField(
            model_name='employee',
            name='employee_number',
            field=models.CharField(
                blank=True,
                max_length=20,
                null=True,
                unique=True,
                verbose_name='Employee Number',
            ),
        ),
    ]

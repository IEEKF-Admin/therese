from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0033_occupation_salary_tables'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='monthly_salary',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    'Snapshot stored when this contract is saved (table in force on '
                    'Valid From, or a manual amount). Live costs use the table in '
                    'force for each calendar month. This is not a month-by-month list.'
                ),
                max_digits=10,
                null=True,
                verbose_name='Monthly Salary (100% workload, snapshot)',
            ),
        ),
    ]

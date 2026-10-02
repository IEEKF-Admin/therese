from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='course',
            name='interval_months',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Rolling from the last completion. Empty unless you use months. Do not set together with calendar years.',
                null=True,
                verbose_name='Repeat every (months)',
            ),
        ),
        migrations.AddField(
            model_name='course',
            name='interval_years',
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    'A completion in year Y covers until 31 December of year Y + N − 1. '
                    'Due from 1 January of year Y + N. Warning is counted from that 31 December. '
                    'Empty unless you use calendar years. Do not set together with months.'
                ),
                null=True,
                verbose_name='Repeat every (calendar years)',
            ),
        ),
        migrations.AlterField(
            model_name='course',
            name='warn_weeks',
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    'Empty = no warning window. For calendar-year courses this is counted '
                    'from 31 December of the covered period, not from the completion date.'
                ),
                null=True,
                verbose_name='Warn weeks before due',
            ),
        ),
    ]

# Generated manually for PSP element enhancements

import django.db.models.deletion
from django.db import migrations, models


def migrate_initial_balances_to_year_estimates(apps, schema_editor):
    InitialBalance = apps.get_model('finances', 'WBSElementInitialBalance')
    YearEstimate = apps.get_model('finances', 'WBSElementYearEstimate')

    for balance in InitialBalance.objects.all().iterator():
        YearEstimate.objects.update_or_create(
            wbs_element_id=balance.wbs_element_id,
            year=balance.year,
            defaults={'funding': balance.initial_balance},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0004_alter_payscale_options_alter_wbselement_options_and_more'),
        ('hr', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='wbselement',
            name='cost_center',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='wbs_elements',
                to='finances.costcenter',
                verbose_name='Cost Center',
            ),
        ),
        migrations.AddField(
            model_name='wbselement',
            name='is_inactive',
            field=models.BooleanField(default=False, verbose_name='Is Inactive'),
        ),
        migrations.AddField(
            model_name='wbselement',
            name='period_end',
            field=models.DateField(blank=True, null=True, verbose_name='Period End'),
        ),
        migrations.AddField(
            model_name='wbselement',
            name='period_start',
            field=models.DateField(blank=True, null=True, verbose_name='Period Start'),
        ),
        migrations.AddField(
            model_name='wbselement',
            name='subject_to_annual_recurrence',
            field=models.BooleanField(default=False, verbose_name='Subject to Annual Recurrence'),
        ),
        migrations.CreateModel(
            name='WBSElementYearEstimate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('year', models.PositiveIntegerField(verbose_name='Year / Period')),
                ('funding', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Funding')),
                ('consumables_estimate', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Consumables Estimate')),
                ('travel_estimate', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Travel Costs Estimate')),
                ('animal_costs_estimate', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Animal Costs Estimate')),
                ('wbs_element', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='year_estimates', to='finances.wbselement', verbose_name='PSP Element')),
            ],
            options={
                'verbose_name': 'PSP Element Year Estimate',
                'verbose_name_plural': 'PSP Element Year Estimates',
                'ordering': ['year'],
                'unique_together': {('wbs_element', 'year')},
            },
        ),
        migrations.RunPython(
            migrate_initial_balances_to_year_estimates,
            migrations.RunPython.noop,
        ),
        migrations.DeleteModel(
            name='WBSElementInitialBalance',
        ),
    ]
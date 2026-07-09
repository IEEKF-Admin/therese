# Generated manually for PSP element and cost center enhancements

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def migrate_cost_center_initial_balances(apps, schema_editor):
    InitialBalance = apps.get_model('finances', 'CostCenterInitialBalance')
    YearEstimate = apps.get_model('finances', 'CostCenterYearEstimate')

    for balance in InitialBalance.objects.all().iterator():
        YearEstimate.objects.update_or_create(
            cost_center_id=balance.cost_center_id,
            year=balance.year,
            defaults={'lomv': balance.initial_balance},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0005_psp_element_year_estimates'),
    ]

    operations = [
        migrations.AddField(
            model_name='costcenter',
            name='third_party_funder_identifier',
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name='Kennzeichen des Drittmittelgebers',
            ),
        ),
        migrations.AddField(
            model_name='costcenter',
            name='third_party_funding_commitment',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='finances/cost_center/third_party_funding/%Y/%m/',
                validators=[django.core.validators.FileExtensionValidator(
                    allowed_extensions=['pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp'],
                )],
                verbose_name='Drittmittelzusage',
            ),
        ),
        migrations.AddField(
            model_name='wbselement',
            name='third_party_funder_identifier',
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name='Kennzeichen des Drittmittelgebers',
            ),
        ),
        migrations.AddField(
            model_name='wbselement',
            name='third_party_funding_commitment',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='finances/psp/third_party_funding/%Y/%m/',
                validators=[django.core.validators.FileExtensionValidator(
                    allowed_extensions=['pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp'],
                )],
                verbose_name='Drittmittelzusage',
            ),
        ),
        migrations.AddField(
            model_name='wbselementyearestimate',
            name='personnel_estimate',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=15,
                null=True,
                verbose_name='Personal',
            ),
        ),
        migrations.AlterModelOptions(
            name='costcenter',
            options={
                'ordering': ['cost_center'],
                'permissions': [('manage_cost_center', 'Can manage cost centers')],
                'verbose_name': 'Cost Center',
                'verbose_name_plural': 'Cost Centers',
            },
        ),
        migrations.CreateModel(
            name='CostCenterYearEstimate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('year', models.PositiveIntegerField(verbose_name='Year / Period')),
                ('lomv', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Lomv')),
                ('consumables_estimate', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Consumables Estimate')),
                ('travel_estimate', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Travel Costs Estimate')),
                ('animal_costs_estimate', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Animal Costs Estimate')),
                ('personnel_estimate', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Personal')),
                ('cost_center', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='year_estimates', to='finances.costcenter', verbose_name='Cost Center')),
            ],
            options={
                'verbose_name': 'Cost Center Year Estimate',
                'verbose_name_plural': 'Cost Center Year Estimates',
                'ordering': ['year'],
                'unique_together': {('cost_center', 'year')},
            },
        ),
        migrations.RunPython(
            migrate_cost_center_initial_balances,
            migrations.RunPython.noop,
        ),
        migrations.DeleteModel(
            name='CostCenterInitialBalance',
        ),
    ]
# Generated manually for .9 cost type, Obligo models, and date_of_update on true spending.

import django.db.models.deletion
from django.db import migrations, models


def _copy_year_to_date_of_update(apps, schema_editor, model_name):
    Model = apps.get_model('finances', model_name)
    for row in Model.objects.all().iterator():
        year = getattr(row, 'year', None)
        if year:
            row.date_of_update = f'{int(year):04d}-01-01'
        else:
            row.date_of_update = '2000-01-01'
        row.save(update_fields=['date_of_update'])


def forwards_true_spending_dates(apps, schema_editor):
    _copy_year_to_date_of_update(apps, schema_editor, 'CostCenterTrueYearlySpending')
    _copy_year_to_date_of_update(apps, schema_editor, 'WBSElementTrueYearlySpending')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0011_cost_center_cost_types_and_true_spending'),
    ]

    operations = [
        # --- Cost-type flag .9 on parents ---
        migrations.AddField(
            model_name='costcenter',
            name='has_internal_service_charges',
            field=models.BooleanField(
                default=False,
                verbose_name='Interne Leistungsverrechnung / Internal service charges',
            ),
        ),
        migrations.AddField(
            model_name='wbselement',
            name='has_internal_service_charges',
            field=models.BooleanField(
                default=False,
                verbose_name='.9 - Interne Leistungsverrechnung / Internal service charges',
            ),
        ),

        # --- Amount field .9 on year estimates (keep year) ---
        migrations.AddField(
            model_name='costcenteryearestimate',
            name='internal_service_charges',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=15,
                null=True,
                verbose_name='.9 - Interne Leistungsverrechnung / Internal service charges',
            ),
        ),
        migrations.AddField(
            model_name='wbselementyearestimate',
            name='internal_service_charges',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=15,
                null=True,
                verbose_name='.9 - Interne Leistungsverrechnung / Internal service charges',
            ),
        ),

        # --- True spending: add .9 amount + date_of_update, migrate from year ---
        migrations.AddField(
            model_name='costcentertrueyearlyspending',
            name='internal_service_charges',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=15,
                null=True,
                verbose_name='.9 - Interne Leistungsverrechnung / Internal service charges',
            ),
        ),
        migrations.AddField(
            model_name='wbselementtrueyearlyspending',
            name='internal_service_charges',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=15,
                null=True,
                verbose_name='.9 - Interne Leistungsverrechnung / Internal service charges',
            ),
        ),
        migrations.AddField(
            model_name='costcentertrueyearlyspending',
            name='date_of_update',
            field=models.DateField(null=True, verbose_name='Date of update'),
        ),
        migrations.AddField(
            model_name='wbselementtrueyearlyspending',
            name='date_of_update',
            field=models.DateField(null=True, verbose_name='Date of update'),
        ),
        migrations.RunPython(forwards_true_spending_dates, noop_reverse),
        migrations.AlterField(
            model_name='costcentertrueyearlyspending',
            name='date_of_update',
            field=models.DateField(verbose_name='Date of update'),
        ),
        migrations.AlterField(
            model_name='wbselementtrueyearlyspending',
            name='date_of_update',
            field=models.DateField(verbose_name='Date of update'),
        ),
        migrations.AlterUniqueTogether(
            name='costcentertrueyearlyspending',
            unique_together={('cost_center', 'date_of_update')},
        ),
        migrations.AlterUniqueTogether(
            name='wbselementtrueyearlyspending',
            unique_together={('wbs_element', 'date_of_update')},
        ),
        migrations.RemoveField(
            model_name='costcentertrueyearlyspending',
            name='year',
        ),
        migrations.RemoveField(
            model_name='wbselementtrueyearlyspending',
            name='year',
        ),
        migrations.AlterModelOptions(
            name='costcentertrueyearlyspending',
            options={
                'ordering': ['-date_of_update'],
                'verbose_name': 'Cost Center True Yearly Spending',
                'verbose_name_plural': 'Cost Center True Yearly Spendings',
            },
        ),
        migrations.AlterModelOptions(
            name='wbselementtrueyearlyspending',
            options={
                'ordering': ['-date_of_update'],
                'verbose_name': 'PSP Element True Yearly Spending',
                'verbose_name_plural': 'PSP Element True Yearly Spendings',
            },
        ),

        # --- Obligo models ---
        migrations.CreateModel(
            name='CostCenterObligo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('material_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.1 - Sachkosten / Material costs',
                )),
                ('personnel_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.2 - Personalkosten / Personnel costs',
                )),
                ('domestic_travel_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.3 - Reisekosten Inland / Domestic travel costs',
                )),
                ('foreign_travel_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.4 - Reisekosten Ausland / Foreign travel costs',
                )),
                ('third_party_investments', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.5 - Drittmittel-Investitionen / Third-party investments',
                )),
                ('publication_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.6 - Publikationskosten / Publication costs',
                )),
                ('animal_husbandry_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.7 - Tierhaltungskosten / Animal husbandry costs',
                )),
                ('transfer_to_third_parties', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.8 - Weitergabe an Dritte / Transfer to third parties',
                )),
                ('internal_service_charges', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.9 - Interne Leistungsverrechnung / Internal service charges',
                )),
                ('date_of_update', models.DateField(verbose_name='Date of update')),
                ('cost_center', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='obligos',
                    to='finances.costcenter',
                    verbose_name='Cost Center',
                )),
            ],
            options={
                'verbose_name': 'Cost Center Obligo',
                'verbose_name_plural': 'Cost Center Obligos',
                'ordering': ['-date_of_update'],
                'unique_together': {('cost_center', 'date_of_update')},
            },
        ),
        migrations.CreateModel(
            name='WBSElementObligo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('material_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.1 - Sachkosten / Material costs',
                )),
                ('personnel_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.2 - Personalkosten / Personnel costs',
                )),
                ('domestic_travel_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.3 - Reisekosten Inland / Domestic travel costs',
                )),
                ('foreign_travel_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.4 - Reisekosten Ausland / Foreign travel costs',
                )),
                ('third_party_investments', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.5 - Drittmittel-Investitionen / Third-party investments',
                )),
                ('publication_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.6 - Publikationskosten / Publication costs',
                )),
                ('animal_husbandry_costs', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.7 - Tierhaltungskosten / Animal husbandry costs',
                )),
                ('transfer_to_third_parties', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.8 - Weitergabe an Dritte / Transfer to third parties',
                )),
                ('internal_service_charges', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    verbose_name='.9 - Interne Leistungsverrechnung / Internal service charges',
                )),
                ('date_of_update', models.DateField(verbose_name='Date of update')),
                ('wbs_element', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='obligos',
                    to='finances.wbselement',
                    verbose_name='PSP Element',
                )),
            ],
            options={
                'verbose_name': 'PSP Element Obligo',
                'verbose_name_plural': 'PSP Element Obligos',
                'ordering': ['-date_of_update'],
                'unique_together': {('wbs_element', 'date_of_update')},
            },
        ),
    ]

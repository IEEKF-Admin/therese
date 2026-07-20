# Purchase order SAP / booking fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0028_reallocation_funding_and_percentage'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseordertask',
            name='kostenart',
            field=models.IntegerField(blank=True, null=True, verbose_name='Kostenart'),
        ),
        migrations.AddField(
            model_name='purchaseordertask',
            name='referenzbeleg_nr',
            field=models.CharField(
                blank=True,
                default='',
                max_length=100,
                verbose_name='Referenzbeleg-Nr',
            ),
        ),
        migrations.AddField(
            model_name='purchaseordertask',
            name='einkaufsbeleg_nr',
            field=models.CharField(
                blank=True,
                default='',
                max_length=100,
                verbose_name='Einkaufsbeleg-Nr',
            ),
        ),
        migrations.AddField(
            model_name='purchaseordertask',
            name='v_kurztext',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                verbose_name='V-Kurztext',
            ),
        ),
        migrations.AddField(
            model_name='purchaseordertask',
            name='v_buchungsdatum',
            field=models.DateField(blank=True, null=True, verbose_name='V-Buchungsdatum'),
        ),
        migrations.AddField(
            model_name='purchaseordertask',
            name='v_belegdatum',
            field=models.DateField(blank=True, null=True, verbose_name='V-Belegdatum'),
        ),
        migrations.AddField(
            model_name='purchaseordertask',
            name='v_istkosten',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=15,
                null=True,
                verbose_name='V-Istkosten',
            ),
        ),
    ]

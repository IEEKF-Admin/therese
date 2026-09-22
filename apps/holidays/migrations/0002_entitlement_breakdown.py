from django.db import migrations, models


def copy_days_into_holidays(apps, schema_editor):
    Entitlement = apps.get_model('holidays', 'HolidayYearEntitlement')
    for row in Entitlement.objects.all():
        row.holidays = row.days or 0
        row.save(update_fields=['holidays'])


class Migration(migrations.Migration):

    dependencies = [
        ('holidays', '0001_holiday_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='holidayyearentitlement',
            name='holidays',
            field=models.DecimalField(
                decimal_places=1, default=0, max_digits=6, verbose_name='Holidays',
            ),
        ),
        migrations.AddField(
            model_name='holidayyearentitlement',
            name='carryover',
            field=models.DecimalField(
                decimal_places=1, default=0, max_digits=6, verbose_name='Carryover',
            ),
        ),
        migrations.AddField(
            model_name='holidayyearentitlement',
            name='special_leave',
            field=models.DecimalField(
                decimal_places=1, default=0, max_digits=6, verbose_name='Special leave',
            ),
        ),
        migrations.RunPython(copy_days_into_holidays, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='holidayyearentitlement',
            name='days',
        ),
        migrations.AlterModelOptions(
            name='holidayyearentitlement',
            options={
                'ordering': ['year'],
                'verbose_name': 'Holiday Year Entitlement',
                'verbose_name_plural': 'Holiday Year Entitlements',
            },
        ),
    ]

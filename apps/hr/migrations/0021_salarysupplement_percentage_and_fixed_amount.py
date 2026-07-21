# Split SalarySupplement into percentage (%) vs fixed_amount (€).

from django.db import migrations, models


def convert_fixed_boolean_to_amount(apps, schema_editor):
    """
    Old schema: percentage + fixed (bool).
    If fixed=True, move the number into fixed_amount and clear percentage.
    """
    SalarySupplement = apps.get_model('hr', 'SalarySupplement')
    # Field ``fixed`` may already be removed in reverse; only run if present.
    for ss in SalarySupplement.objects.all().iterator():
        # After AddField fixed_amount / AlterField percentage, both exist;
        # ``fixed`` still exists until RemoveField.
        is_fixed = getattr(ss, 'fixed', False)
        if is_fixed and ss.percentage is not None:
            ss.fixed_amount = ss.percentage
            ss.percentage = None
            ss.save(update_fields=['fixed_amount', 'percentage'])


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0020_salarysupplement_contract_fixed'),
    ]

    operations = [
        migrations.AddField(
            model_name='salarysupplement',
            name='fixed_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Fixed euro amount per month. Leave empty if using a percentage.',
                max_digits=10,
                null=True,
                verbose_name='Fixed amount (€)',
            ),
        ),
        migrations.AlterField(
            model_name='salarysupplement',
            name='percentage',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Percentage of monthly salary. Leave empty if using a fixed amount.',
                max_digits=5,
                null=True,
                verbose_name='Percentage (%)',
            ),
        ),
        migrations.RunPython(convert_fixed_boolean_to_amount, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='salarysupplement',
            name='fixed',
        ),
    ]

# FundingAllocation must belong to a Contract.

from django.db import migrations, models
import django.db.models.deletion


def assign_or_delete_funding_allocations(apps, schema_editor):
    """
    Link existing FAs to a contract of the same employee when possible;
    delete the rest (product decision: unassigned FAs may be dropped).
    """
    FundingAllocation = apps.get_model('hr', 'FundingAllocation')
    Contract = apps.get_model('hr', 'Contract')

    for fa in FundingAllocation.objects.all().iterator():
        contracts = list(
            Contract.objects.filter(employee_id=fa.employee_id).order_by(
                '-is_active', '-valid_from', 'pk'
            )
        )
        if not contracts:
            fa.delete()
            continue

        chosen = None
        for c in contracts:
            # Prefer date overlap when FA has start_date
            c_end = c.valid_until
            fa_end = fa.end_date
            if fa.start_date and c.valid_from:
                if fa.start_date < c.valid_from:
                    continue
                if c_end and fa.start_date > c_end:
                    continue
            chosen = c
            if c.is_active:
                break
        if chosen is None:
            chosen = contracts[0]
        fa.contract_id = chosen.pk
        # Expired contract → FA inactive
        if not chosen.is_active:
            fa.is_active = False
        fa.save(update_fields=['contract_id', 'is_active'])

    # Drop any still unassigned (should be none)
    FundingAllocation.objects.filter(contract__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0018_contract_fa_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='fundingallocation',
            name='contract',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='funding_allocations',
                to='hr.contract',
                verbose_name='Contract',
            ),
        ),
        migrations.RunPython(assign_or_delete_funding_allocations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='fundingallocation',
            name='contract',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='funding_allocations',
                to='hr.contract',
                verbose_name='Contract',
            ),
        ),
    ]

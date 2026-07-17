from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models
from django.db.models import Q


def convert_hours_to_percentage_and_copy_plan_position(apps, schema_editor):
    FundingAllocation = apps.get_model('hr', 'FundingAllocation')
    Contract = apps.get_model('hr', 'Contract')
    GlobalSetting = apps.get_model('core', 'GlobalSetting')

    try:
        default_hours = GlobalSetting.objects.get(pk=1).default_weekly_hours
    except GlobalSetting.DoesNotExist:
        default_hours = Decimal('39.00')
    if not default_hours or default_hours <= 0:
        default_hours = Decimal('39.00')

    for allocation in FundingAllocation.objects.all().iterator():
        hours = allocation.weekly_hours_allocated
        contract = (
            Contract.objects.filter(
                employee_id=allocation.employee_id,
                valid_from__lte=allocation.start_date,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=allocation.start_date))
            .order_by('-valid_from')
            .first()
        )
        if contract is None:
            contract = (
                Contract.objects.filter(employee_id=allocation.employee_id)
                .order_by('-valid_from')
                .first()
            )

        weekly = contract.weekly_hours if contract and contract.weekly_hours else default_hours
        if weekly and weekly > 0 and hours is not None:
            percentage = (Decimal(hours) / Decimal(weekly) * Decimal('100')).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )
        else:
            percentage = Decimal(hours or 0)

        plan_position = ''
        if contract and getattr(contract, 'plan_position_number', ''):
            plan_position = contract.plan_position_number

        allocation.workhours_percentage = percentage
        allocation.plan_position_number = plan_position or ''
        allocation.save(update_fields=['workhours_percentage', 'plan_position_number'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0014_contract_plan_position_number'),
        ('core', '0003_globalsetting_true_cost_multiplicator'),
    ]

    operations = [
        migrations.AddField(
            model_name='fundingallocation',
            name='workhours_percentage',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('100.00'),
                help_text="Share of the employee's contract weekly hours (0–100+).",
                max_digits=6,
                verbose_name='Percentage of Workhours',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='fundingallocation',
            name='plan_position_number',
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name='Plan Position Number',
            ),
        ),
        migrations.RunPython(
            convert_hours_to_percentage_and_copy_plan_position,
            noop_reverse,
        ),
        migrations.RemoveField(
            model_name='fundingallocation',
            name='weekly_hours_allocated',
        ),
        migrations.RemoveField(
            model_name='contract',
            name='plan_position_number',
        ),
    ]

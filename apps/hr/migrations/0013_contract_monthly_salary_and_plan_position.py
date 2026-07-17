from django.db import migrations, models


def copy_employee_salary_to_contracts(apps, schema_editor):
    """Move legacy Employee.monthly_salary onto the latest contract when empty."""
    Employee = apps.get_model('hr', 'Employee')
    Contract = apps.get_model('hr', 'Contract')
    PayScale = apps.get_model('finances', 'PayScale')

    # Latest effective payscale per (group, level)
    payscale_map = {}
    for ps in PayScale.objects.all().order_by('pay_scale_group', 'experience_level', '-effective_as_of'):
        key = (ps.pay_scale_group, ps.experience_level)
        if key not in payscale_map:
            payscale_map[key] = ps.monthly_salary

    for emp in Employee.objects.all():
        contracts = list(Contract.objects.filter(employee_id=emp.pk).order_by('-valid_from'))
        if not contracts:
            continue
        for contract in contracts:
            if contract.monthly_salary is not None:
                continue
            if contract.pay_scale_group and contract.experience_level is not None:
                salary = payscale_map.get((contract.pay_scale_group, contract.experience_level))
                if salary is not None:
                    contract.monthly_salary = salary
                    contract.save(update_fields=['monthly_salary'])
                    continue
            if emp.monthly_salary is not None and contract == contracts[0]:
                contract.monthly_salary = emp.monthly_salary
                contract.save(update_fields=['monthly_salary'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0012_funding_allocation_cost_center'),
        ('finances', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='monthly_salary',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='Monthly Salary',
            ),
        ),
        migrations.AlterField(
            model_name='contract',
            name='job_number',
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name='Plan Position Number',
            ),
        ),
        migrations.RunPython(copy_employee_salary_to_contracts, noop_reverse),
    ]

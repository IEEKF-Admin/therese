# SalarySupplement belongs to Contract; add fixed flag.

from django.db import migrations, models
import django.db.models.deletion


def assign_or_delete_salary_supplements(apps, schema_editor):
    SalarySupplement = apps.get_model('hr', 'SalarySupplement')
    Contract = apps.get_model('hr', 'Contract')

    for ss in SalarySupplement.objects.all().iterator():
        contracts = list(
            Contract.objects.filter(employee_id=ss.employee_id).order_by(
                '-is_active', '-valid_from', 'pk'
            )
        )
        if not contracts:
            ss.delete()
            continue
        chosen = next((c for c in contracts if c.is_active), contracts[0])
        ss.contract_id = chosen.pk
        ss.save(update_fields=['contract_id'])

    SalarySupplement.objects.filter(contract__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0019_fundingallocation_contract'),
    ]

    operations = [
        migrations.AddField(
            model_name='salarysupplement',
            name='contract',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='salary_supplements',
                to='hr.contract',
                verbose_name='Contract',
            ),
        ),
        migrations.AddField(
            model_name='salarysupplement',
            name='fixed',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'If checked, this supplement is a fixed amount rather than '
                    'percentage-based.'
                ),
                verbose_name='Fixed',
            ),
        ),
        migrations.RunPython(assign_or_delete_salary_supplements, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='salarysupplement',
            name='contract',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='salary_supplements',
                to='hr.contract',
                verbose_name='Contract',
            ),
        ),
        migrations.AlterModelOptions(
            name='salarysupplement',
            options={
                'ordering': ['contract', '-created_at'],
                'verbose_name': 'Salary Supplement',
                'verbose_name_plural': 'Salary Supplements',
            },
        ),
    ]

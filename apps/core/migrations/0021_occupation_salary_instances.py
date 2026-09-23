from datetime import date

import django.db.models.deletion
from django.db import migrations, models


def create_instances_and_attach_rows(apps, schema_editor):
    Table = apps.get_model('core', 'OccupationSalaryTable')
    Instance = apps.get_model('core', 'OccupationSalaryInstance')
    Row = apps.get_model('core', 'OccupationSalaryRow')
    fallback = date(2000, 1, 1)
    for table in Table.objects.all():
        instance = Instance.objects.create(table=table, effective_as_of=fallback)
        Row.objects.filter(table_id=table.pk).update(instance=instance)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_holiday_email_defaults_de'),
    ]

    operations = [
        migrations.CreateModel(
            name='OccupationSalaryInstance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('effective_as_of', models.DateField(verbose_name='Effective as of')),
                ('table', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='instances',
                    to='core.occupationsalarytable',
                    verbose_name='Table',
                )),
            ],
            options={
                'verbose_name': 'Occupational salary instance',
                'verbose_name_plural': 'Occupational salary instances',
                'ordering': ['-effective_as_of', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='occupationsalaryinstance',
            constraint=models.UniqueConstraint(
                fields=('table', 'effective_as_of'),
                name='occupation_salary_instance_date_uniq',
            ),
        ),
        migrations.AddField(
            model_name='occupationsalaryrow',
            name='instance',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='rows',
                to='core.occupationsalaryinstance',
                verbose_name='Instance',
            ),
        ),
        migrations.RunPython(create_instances_and_attach_rows, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='occupationsalaryrow',
            name='occupation_salary_row_hours_uniq',
        ),
        migrations.RemoveField(
            model_name='occupationsalaryrow',
            name='table',
        ),
        migrations.AlterField(
            model_name='occupationsalaryrow',
            name='instance',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='rows',
                to='core.occupationsalaryinstance',
                verbose_name='Instance',
            ),
        ),
        migrations.AddConstraint(
            model_name='occupationsalaryrow',
            constraint=models.UniqueConstraint(
                fields=('instance', 'weekly_hours'),
                name='occupation_salary_row_hours_uniq',
            ),
        ),
    ]

from django.db import migrations


def hide_extern_pi(apps, schema_editor):
    Employee = apps.get_model('hr', 'Employee')
    Workgroup = apps.get_model('hr', 'Workgroup')
    employee = Employee.objects.filter(
        first_name='Extern',
        last_name='Externssohn',
        is_external=True,
    ).first()
    if employee is None:
        employee = Employee.objects.create(
            first_name='Extern',
            last_name='Externssohn',
            is_external=True,
        )
    if getattr(employee, 'user_id', None):
        employee.user_id = None
        employee.save()
    workgroup = Workgroup.objects.filter(short_name='Extern').first()
    if workgroup is None:
        workgroup = Workgroup.objects.create(
            short_name='Extern',
            long_name='Extern',
            pi=employee,
        )
    workgroup.members.remove(employee)


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0031_extern_workgroup'),
    ]

    operations = [
        migrations.RunPython(hide_extern_pi, migrations.RunPython.noop),
    ]

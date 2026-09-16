from django.db import migrations


def hide_extern_pi(apps, schema_editor):
    from apps.hr.extern import ensure_extern_defaults

    ensure_extern_defaults()


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0031_extern_workgroup'),
    ]

    operations = [
        migrations.RunPython(hide_extern_pi, migrations.RunPython.noop),
    ]

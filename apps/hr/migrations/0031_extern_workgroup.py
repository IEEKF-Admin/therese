from django.db import migrations


def seed_extern(apps, schema_editor):
    from apps.hr.extern import ensure_extern_defaults

    ensure_extern_defaults()


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0030_contract_fa_is_archived'),
    ]

    operations = [
        migrations.RunPython(seed_extern, migrations.RunPython.noop),
    ]

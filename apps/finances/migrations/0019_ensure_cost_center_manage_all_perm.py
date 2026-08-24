from django.db import migrations


def ensure_cost_center_permissions(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    CostCenter = apps.get_model('finances', 'CostCenter')
    ct, _created = ContentType.objects.get_or_create(
        app_label='finances',
        model='costcenter',
    )
    Permission.objects.update_or_create(
        content_type=ct,
        codename='manage_all_cost_centers',
        defaults={
            'name': 'Can manage all cost centers institute-wide (ignore workgroup scope)',
        },
    )
    Permission.objects.filter(
        content_type=ct,
        codename='manage_cost_center',
    ).update(name='Can manage cost centers in own workgroups')


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0018_cost_center_work_group_and_funding_analysis'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(ensure_cost_center_permissions, migrations.RunPython.noop),
    ]

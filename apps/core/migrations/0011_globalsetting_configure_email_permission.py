from django.db import migrations


def ensure_configure_email_permission(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ct, _created = ContentType.objects.get_or_create(
        app_label='core',
        model='globalsetting',
    )
    Permission.objects.update_or_create(
        content_type=ct,
        codename='configure_email',
        defaults={'name': 'Can configure outbound email'},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_globalsetting_show_add_employee_on_reallocation'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='globalsetting',
            options={
                'permissions': [('configure_email', 'Can configure outbound email')],
                'verbose_name': 'Global Setting',
                'verbose_name_plural': 'Global Settings',
            },
        ),
        migrations.RunPython(ensure_configure_email_permission, migrations.RunPython.noop),
    ]

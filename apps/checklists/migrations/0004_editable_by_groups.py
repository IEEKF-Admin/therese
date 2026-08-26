from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('checklists', '0003_psp_all_and_permission_labels'),
    ]

    operations = [
        migrations.AddField(
            model_name='checklisttemplatenode',
            name='editable_by_groups',
            field=models.ManyToManyField(
                blank=True,
                related_name='editable_checklist_nodes',
                to='auth.group',
                verbose_name='Editable by Django groups',
            ),
        ),
    ]

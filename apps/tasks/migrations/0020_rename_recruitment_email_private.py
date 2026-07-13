from django.db import migrations, models


def rename_recruitment_field_rules(apps, schema_editor):
    RecruitmentJobFieldRule = apps.get_model('tasks', 'RecruitmentJobFieldRule')
    RecruitmentJobFieldRule.objects.filter(field_key='email_professional').update(
        field_key='email_private',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0019_recruitment_job_payscale'),
    ]

    operations = [
        migrations.RenameField(
            model_name='personnelrecruitmenttask',
            old_name='email_professional',
            new_name='email_private',
        ),
        migrations.AlterField(
            model_name='personnelrecruitmenttask',
            name='email_private',
            field=models.EmailField(max_length=254, verbose_name='Private Email'),
        ),
        migrations.RunPython(rename_recruitment_field_rules, migrations.RunPython.noop),
    ]
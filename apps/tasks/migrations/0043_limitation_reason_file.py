from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0042_occupation_salary_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='personnelcontractextensiontask',
            name='limitation_reason_file',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='extension_tasks/limitation_reason/',
                verbose_name='Limitation Reason',
            ),
        ),
        migrations.AddField(
            model_name='personnelcontractextensiontask',
            name='limitation_reason_generated',
            field=models.BooleanField(
                default=False,
                verbose_name='Limitation Reason PDF generated from text',
            ),
        ),
        migrations.AddField(
            model_name='personnelrecruitmenttask',
            name='limitation_reason_file',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='recruitment_tasks/limitation_reason/',
                verbose_name='Limitation Reason',
            ),
        ),
        migrations.AddField(
            model_name='personnelrecruitmenttask',
            name='limitation_reason_generated',
            field=models.BooleanField(
                default=False,
                verbose_name='Limitation Reason PDF generated from text',
            ),
        ),
    ]

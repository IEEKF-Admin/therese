import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0009_rename_measles_document_type'),
        ('tasks', '0019_recruitment_job_payscale'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='job',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='employees',
                to='tasks.recruitmentjob',
                verbose_name='Job',
            ),
        ),
    ]
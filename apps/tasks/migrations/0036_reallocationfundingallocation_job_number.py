from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0035_recruitment_standard_job_and_qualification'),
    ]

    operations = [
        migrations.AddField(
            model_name='reallocationfundingallocation',
            name='job_number',
            field=models.CharField(blank=True, max_length=50, verbose_name='Job Number'),
        ),
    ]

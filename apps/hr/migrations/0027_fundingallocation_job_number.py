from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0026_personnel_import_flags_tolerance'),
    ]

    operations = [
        migrations.AddField(
            model_name='fundingallocation',
            name='job_number',
            field=models.CharField(blank=True, max_length=50, verbose_name='Job Number'),
        ),
    ]

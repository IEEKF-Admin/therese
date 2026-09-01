from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0027_fundingallocation_job_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='weekly_hours',
            field=models.DecimalField(
                decimal_places=3,
                max_digits=6,
                verbose_name='Weekly Working Hours',
            ),
        ),
    ]

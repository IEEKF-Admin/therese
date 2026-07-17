from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0013_contract_monthly_salary_and_plan_position'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='job_number',
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name='Job Number',
            ),
        ),
        migrations.AddField(
            model_name='contract',
            name='plan_position_number',
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name='Plan Position Number',
            ),
        ),
    ]

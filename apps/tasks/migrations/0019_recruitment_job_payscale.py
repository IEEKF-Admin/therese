from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0018_recruitment_jobs_and_field_rules'),
    ]

    operations = [
        migrations.AddField(
            model_name='recruitmentjob',
            name='experience_level',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Experience Level'),
        ),
        migrations.AddField(
            model_name='recruitmentjob',
            name='pay_scale_group',
            field=models.CharField(blank=True, max_length=50, verbose_name='Pay Scale Group'),
        ),
    ]
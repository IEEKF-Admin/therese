from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0002_interval_years'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='substitutes_for',
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    'Completing this course in a calendar year also satisfies those courses for that year. '
                    'When this course is due, those courses are not due. Requires calendar years. '
                    'The cycle is personal: from this employee\'s last completion of this course, or if none '
                    'from their first completion of a replaced course (as if this course was done the year before).'
                ),
                related_name='substituted_by',
                to='courses.course',
                verbose_name='May replace',
            ),
        ),
    ]

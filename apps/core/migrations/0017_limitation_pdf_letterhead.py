from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_occupation_salary_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsetting',
            name='limitation_pdf_letterhead',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'HTML letterhead at the top of auto-generated Limitation Reason PDFs '
                    '(Personnel Recruitment and Contract Extension).'
                ),
                verbose_name='Limitation Reason PDF letterhead',
            ),
        ),
    ]

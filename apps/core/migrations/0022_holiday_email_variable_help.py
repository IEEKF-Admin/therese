from django.db import migrations, models


HELP = 'See the holiday email variable list in Global Settings.'


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_occupation_salary_instances'),
    ]

    operations = [
        migrations.AlterField(
            model_name='globalsetting',
            name='holiday_request_email_subject',
            field=models.CharField(
                blank=True,
                default='Urlaubsantrag – {{ applicant_name }}',
                help_text=HELP,
                max_length=200,
                verbose_name='Request email subject',
            ),
        ),
        migrations.AlterField(
            model_name='globalsetting',
            name='holiday_request_email_html',
            field=models.TextField(
                blank=True,
                help_text=HELP,
                verbose_name='Request email body (HTML)',
            ),
        ),
        migrations.AlterField(
            model_name='globalsetting',
            name='holiday_cancel_email_subject',
            field=models.CharField(
                blank=True,
                default='Urlaubsstornierung – {{ applicant_name }}',
                help_text=HELP,
                max_length=200,
                verbose_name='Cancellation email subject',
            ),
        ),
        migrations.AlterField(
            model_name='globalsetting',
            name='holiday_cancel_email_html',
            field=models.TextField(
                blank=True,
                help_text=HELP,
                verbose_name='Cancellation email body (HTML)',
            ),
        ),
    ]

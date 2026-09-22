from django.db import migrations, models


def copy_old_holiday_email(apps, schema_editor):
    Setting = apps.get_model('core', 'GlobalSetting')
    for row in Setting.objects.all():
        subject = (getattr(row, 'holiday_email_subject', '') or '').strip()
        html = (getattr(row, 'holiday_email_html', '') or '').strip()
        update = []
        if subject:
            row.holiday_request_email_subject = subject
            update.append('holiday_request_email_subject')
        if html:
            row.holiday_request_email_html = html
            update.append('holiday_request_email_html')
        if update:
            row.save(update_fields=update)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_inventory_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsetting',
            name='holiday_request_email_subject',
            field=models.CharField(
                blank=True,
                default='Holiday request – {{ applicant_name }}',
                help_text='Variables: {{ applicant_name }}, {{ employee_number }}, {{ periods }}, {{ day_count }}',
                max_length=200,
                verbose_name='Request email subject',
            ),
        ),
        migrations.AddField(
            model_name='globalsetting',
            name='holiday_request_email_html',
            field=models.TextField(
                blank=True,
                help_text='Variables: {{ applicant_name }}, {{ employee_number }}, {{ periods }}, {{ day_count }}',
                verbose_name='Request email body (HTML)',
            ),
        ),
        migrations.AddField(
            model_name='globalsetting',
            name='holiday_cancel_email_subject',
            field=models.CharField(
                blank=True,
                default='Holiday cancellation – {{ applicant_name }}',
                help_text='Variables: {{ applicant_name }}, {{ employee_number }}, {{ periods }}, {{ day_count }}',
                max_length=200,
                verbose_name='Cancellation email subject',
            ),
        ),
        migrations.AddField(
            model_name='globalsetting',
            name='holiday_cancel_email_html',
            field=models.TextField(
                blank=True,
                help_text='Variables: {{ applicant_name }}, {{ employee_number }}, {{ periods }}, {{ day_count }}',
                verbose_name='Cancellation email body (HTML)',
            ),
        ),
        migrations.RunPython(copy_old_holiday_email, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='globalsetting',
            name='holiday_email_subject',
        ),
        migrations.RemoveField(
            model_name='globalsetting',
            name='holiday_email_html',
        ),
        migrations.AlterField(
            model_name='globalsetting',
            name='holiday_email_recipients',
            field=models.TextField(
                blank=True,
                help_text=(
                    'Comma-separated addresses. Request and cancellation emails are also '
                    'sent to the employee.'
                ),
                verbose_name='Holiday email recipients',
            ),
        ),
        migrations.AlterField(
            model_name='globalsetting',
            name='holidays_planning_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Employees can request leave and see remaining days.',
                verbose_name='Holidays: planning',
            ),
        ),
        migrations.AlterField(
            model_name='globalsetting',
            name='holidays_approval_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Workgroup / super approvers decide requests.',
                verbose_name='Holidays: approval',
            ),
        ),
    ]

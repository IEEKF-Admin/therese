from django.db import migrations, models


OLD_REQUEST = 'Holiday request – {{ applicant_name }}'
NEW_REQUEST = 'Urlaubsantrag – {{ applicant_name }}'
OLD_CANCEL = 'Holiday cancellation – {{ applicant_name }}'
NEW_CANCEL = 'Urlaubsstornierung – {{ applicant_name }}'


def update_english_defaults(apps, schema_editor):
    Setting = apps.get_model('core', 'GlobalSetting')
    for row in Setting.objects.all():
        update = []
        if (row.holiday_request_email_subject or '') == OLD_REQUEST:
            row.holiday_request_email_subject = NEW_REQUEST
            update.append('holiday_request_email_subject')
        if (row.holiday_cancel_email_subject or '') == OLD_CANCEL:
            row.holiday_cancel_email_subject = NEW_CANCEL
            update.append('holiday_cancel_email_subject')
        if update:
            row.save(update_fields=update)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_holiday_request_cancel_emails'),
    ]

    operations = [
        migrations.AlterField(
            model_name='globalsetting',
            name='holiday_request_email_subject',
            field=models.CharField(
                blank=True,
                default='Urlaubsantrag – {{ applicant_name }}',
                help_text='Variables: {{ applicant_name }}, {{ employee_number }}, {{ periods }}, {{ day_count }}, {{ holiday_analysis }}',
                max_length=200,
                verbose_name='Request email subject',
            ),
        ),
        migrations.AlterField(
            model_name='globalsetting',
            name='holiday_cancel_email_subject',
            field=models.CharField(
                blank=True,
                default='Urlaubsstornierung – {{ applicant_name }}',
                help_text='Variables: {{ applicant_name }}, {{ employee_number }}, {{ periods }}, {{ day_count }}, {{ holiday_analysis }}',
                max_length=200,
                verbose_name='Cancellation email subject',
            ),
        ),
        migrations.RunPython(update_english_defaults, migrations.RunPython.noop),
    ]

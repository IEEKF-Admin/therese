from django.db import migrations, models


HELP = (
    'See the holiday email variable list in Global Settings. '
    'Empty: that email is not sent.'
)

REQUEST_HTML = (
    '<p>{{ first_name }} {{ last_name }}<br>'
    '{{ job_title }}<br>'
    '{{ department }}</p>'
    '<p>{{ place_date }}</p>'
    '<p><strong>URLAUBSANTRAG</strong></p>'
    '<p>Ich bitte um Urlaub vom {{ vacation_from }} bis {{ vacation_until }}'
    ' ({{ day_count }} Arbeitstage).</p>'
    '<p>Anlass, Zweck des Urlaubs: {{ purpose }}<br>'
    'Urlaubsanschrift: {{ leave_address }}<br>'
    'Vertreter/in: {{ deputy }}</p>'
    '<p>Zustehender Jahresurlaub: {{ annual_leave }} Arbeitstage<br>'
    'Zusatz-Sonder-Urlaub: {{ special_leave }}<br>'
    'Rest aus Vorjahr: {{ carryover }}<br>'
    'zusammen: {{ available }}<br>'
    'davon bereits erhalten/genehmigt: {{ already_granted }}<br>'
    'jetzt erbeten: {{ now_requested }}<br>'
    'verbleibender Resturlaub: {{ remaining_leave }} Arbeitstage</p>'
    '<p>Freigegeben von: {{ approver_name }}</p>'
)

CANCEL_HTML = (
    '<p>{{ applicant_name }} (Personalnummer {{ employee_number }}) '
    'hat Urlaub storniert:</p><p>{{ periods }}</p>'
    '<p>Tage: {{ day_count }}</p>'
)


def fill_empty_holiday_email_html(apps, schema_editor):
    Setting = apps.get_model('core', 'GlobalSetting')
    for row in Setting.objects.all():
        update = []
        if not (row.holiday_request_email_html or '').strip():
            row.holiday_request_email_html = REQUEST_HTML
            update.append('holiday_request_email_html')
        if not (row.holiday_cancel_email_html or '').strip():
            row.holiday_cancel_email_html = CANCEL_HTML
            update.append('holiday_cancel_email_html')
        if update:
            row.save(update_fields=update)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0027_wordpress_positions'),
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
                default=REQUEST_HTML,
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
                default=CANCEL_HTML,
                help_text=HELP,
                verbose_name='Cancellation email body (HTML)',
            ),
        ),
        migrations.RunPython(fill_empty_holiday_email_html, migrations.RunPython.noop),
    ]

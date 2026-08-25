from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_funding_analysis_link_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='loginpopupconfig',
            name='show_popup',
            field=models.BooleanField(
                default=True,
                help_text='Show the popup message at login when this trigger fires.',
                verbose_name='Show popup',
            ),
        ),
        migrations.AddField(
            model_name='loginpopupconfig',
            name='send_email',
            field=models.BooleanField(
                default=False,
                help_text='Send the email template when this trigger fires. Edit subject and body on Email environment.',
                verbose_name='Send email',
            ),
        ),
        migrations.AddField(
            model_name='loginpopupconfig',
            name='email_subject',
            field=models.CharField(
                blank=True,
                help_text='Subject line. Placeholders such as {{ first_name }} are replaced when sending.',
                max_length=200,
                verbose_name='Email subject',
            ),
        ),
        migrations.AddField(
            model_name='loginpopupconfig',
            name='email_html',
            field=models.TextField(
                blank=True,
                help_text='HTML email body. Edited on the Email environment page.',
                verbose_name='Email body (HTML)',
            ),
        ),
        migrations.AlterField(
            model_name='loginpopupconfig',
            name='text',
            field=models.TextField(
                blank=True,
                help_text='Plain-text message for the login popup. Email body is configured separately.',
            ),
        ),
    ]

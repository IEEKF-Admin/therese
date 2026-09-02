from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_holiday_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountemailtemplate',
            name='attachment',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='account_email_attachments/%Y/%m/',
                verbose_name='Attachment',
            ),
        ),
    ]

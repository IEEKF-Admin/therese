from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_loginpopupconfig_schedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='loginpopupconfig',
            name='schedule_require_lists',
            field=models.TextField(
                blank=True,
                help_text='Comma-separated list variable keys that must be non-empty before a scheduled email is sent.',
            ),
        ),
    ]

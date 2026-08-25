from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_loginpopupconfig_email_templates'),
    ]

    operations = [
        migrations.CreateModel(
            name='TriggerEmailSend',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference_key', models.CharField(max_length=191)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                (
                    'config',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='email_sends',
                        to='accounts.loginpopupconfig',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='trigger_email_sends',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'Trigger Email Send',
                'verbose_name_plural': 'Trigger Email Sends',
            },
        ),
        migrations.AddConstraint(
            model_name='triggeremailsend',
            constraint=models.UniqueConstraint(
                fields=('config', 'user', 'reference_key'),
                name='unique_trigger_email_send',
            ),
        ),
    ]

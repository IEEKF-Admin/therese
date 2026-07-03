# Generated manually for login popup audience + contract acknowledgements

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


CONTRACT_TRIGGERS = ('contract_ending_soon', 'any_contract_ending_soon')


def migrate_shown_to_global_acknowledgements(apps, schema_editor):
    Config = apps.get_model('accounts', 'LoginPopupConfig')
    Ack = apps.get_model('accounts', 'LoginPopupAcknowledgement')
    User = apps.get_model('accounts', 'CustomUser')
    through_model = Config.shown_to_users.through

    for row in through_model.objects.all().iterator():
        config_id = getattr(row, 'loginpopupconfig_id', None)
        user_id = getattr(row, 'customuser_id', None)
        if not config_id or not user_id:
            continue
        config = Config.objects.filter(pk=config_id).first()
        if not config or config.trigger in CONTRACT_TRIGGERS:
            continue
        if not User.objects.filter(pk=user_id).exists():
            continue
        Ack.objects.get_or_create(
            config_id=config_id,
            user_id=user_id,
            reference_key='global',
            defaults={'shown_at': timezone.now()},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_loginpopupconfig_shown_to_users'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('hr', '0002_workgroup'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginPopupAcknowledgement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference_key', models.CharField(help_text="'global' for one-time triggers, or 'contract:<pk>' per contract.", max_length=64)),
                ('shown_at', models.DateTimeField(auto_now_add=True)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='acknowledgements', to='accounts.loginpopupconfig')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='login_popup_acknowledgements', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Login Popup Acknowledgement',
                'verbose_name_plural': 'Login Popup Acknowledgements',
            },
        ),
        migrations.AddConstraint(
            model_name='loginpopupacknowledgement',
            constraint=models.UniqueConstraint(fields=('config', 'user', 'reference_key'), name='unique_login_popup_ack'),
        ),
        migrations.AddField(
            model_name='loginpopupconfig',
            name='target_groups',
            field=models.ManyToManyField(blank=True, help_text='If set, users in these Django groups also see this popup.', related_name='targeted_login_popups', to='auth.group', verbose_name='Target Django groups'),
        ),
        migrations.AddField(
            model_name='loginpopupconfig',
            name='target_users',
            field=models.ManyToManyField(blank=True, help_text='If set, only these users see this popup (combined with other targets below).', related_name='targeted_login_popups', to=settings.AUTH_USER_MODEL, verbose_name='Target users'),
        ),
        migrations.AddField(
            model_name='loginpopupconfig',
            name='target_workgroups',
            field=models.ManyToManyField(blank=True, help_text='If set, members of these work groups also see this popup.', related_name='targeted_login_popups', to='hr.workgroup', verbose_name='Target work groups'),
        ),
        migrations.RunPython(
            migrate_shown_to_global_acknowledgements,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='loginpopupconfig',
            name='shown_to_users',
        ),
    ]
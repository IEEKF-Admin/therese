from django.db import migrations, models


def create_default_account_email_templates(apps, schema_editor):
    AccountEmailTemplate = apps.get_model('accounts', 'AccountEmailTemplate')
    defaults = [
        (
            'user_created',
            'Your THERESE account',
            (
                '<p>Hello {{ prefix }} {{ first_name }} {{ last_name }},</p>'
                '<p>A login for THERESE has been created for you.</p>'
                '<p>Login URL: {{ login_url }}<br>'
                'Username: {{ username }}<br>'
                'Password: {{ password }}</p>'
                '<p>You will be asked to choose a new password after signing in.</p>'
            ),
        ),
        (
            'password_reset',
            'Your THERESE password was reset',
            (
                '<p>Hello {{ prefix }} {{ first_name }} {{ last_name }},</p>'
                '<p>Your THERESE password has been reset.</p>'
                '<p>Login URL: {{ login_url }}<br>'
                'Username: {{ username }}<br>'
                'Password: {{ password }}</p>'
                '<p>You will be asked to choose a new password after signing in.</p>'
            ),
        ),
    ]
    for kind, subject, body in defaults:
        AccountEmailTemplate.objects.get_or_create(
            kind=kind,
            defaults={'subject': subject, 'body_html': body},
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_triggeremailsend'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='customuser',
            options={
                'permissions': [
                    (
                        'reset_user_password',
                        'Can reset user passwords and edit account emails',
                    ),
                ],
                'verbose_name': 'User',
                'verbose_name_plural': 'Users',
            },
        ),
        migrations.CreateModel(
            name='AccountEmailTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'kind',
                    models.CharField(
                        choices=[
                            ('user_created', 'New user account'),
                            ('password_reset', 'Password reset'),
                        ],
                        max_length=32,
                        unique=True,
                    ),
                ),
                ('subject', models.CharField(max_length=200)),
                ('body_html', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Account Email Template',
                'verbose_name_plural': 'Account Email Templates',
            },
        ),
        migrations.RunPython(create_default_account_email_templates, noop_reverse),
    ]

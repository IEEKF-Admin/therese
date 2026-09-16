from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_globalsetting_employee_expiring_soon_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsetting',
            name='chemicals_enabled',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Master switch. When off, Chemical Items, Substances (CAS), '
                    'purchase-order CAS checks, and related popups are hidden; '
                    'the options below are ignored.'
                ),
                verbose_name='Chemicals module',
            ),
        ),
    ]

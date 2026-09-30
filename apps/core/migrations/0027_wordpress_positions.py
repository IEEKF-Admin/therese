from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_smtp_and_sympa'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsetting',
            name='wordpress_positions',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'One allowed position value per line. Used as the Position dropdown '
                    'when publishing an employee to WordPress.'
                ),
                verbose_name='WordPress positions',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_loginpopup_audience_and_acknowledgements'),
    ]

    operations = [
        migrations.AddField(
            model_name='loginpopupconfig',
            name='audience_match_mode',
            field=models.CharField(
                choices=[('or', 'OR — match any selected criterion'), ('and', 'AND — match all selected criteria')],
                default='or',
                help_text='How user, work group, and Django group targets are combined.',
                max_length=3,
                verbose_name='Audience match mode',
            ),
        ),
    ]
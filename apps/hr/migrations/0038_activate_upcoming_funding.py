from django.db import migrations, models
from django.utils import timezone


def activate_upcoming_funding(apps, schema_editor):
    today = timezone.now().date()
    FundingAllocation = apps.get_model('hr', 'FundingAllocation')
    FundingAllocation.objects.filter(
        start_date__gt=today,
        is_archived=False,
        is_active=False,
        contract__is_active=True,
        contract__is_archived=False,
    ).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0037_wordpress'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fundingallocation',
            name='is_active',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Yes/No. Can be set manually. Automatically set to No when '
                    'Valid Until is in the past. Upcoming allocations stay Yes.'
                ),
                verbose_name='Active',
            ),
        ),
        migrations.RunPython(activate_upcoming_funding, migrations.RunPython.noop),
    ]

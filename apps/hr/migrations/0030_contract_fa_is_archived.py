from django.db import migrations, models
from django.utils import timezone


def mark_ended_as_archived(apps, schema_editor):
    today = timezone.now().date()
    Contract = apps.get_model('hr', 'Contract')
    FundingAllocation = apps.get_model('hr', 'FundingAllocation')
    Contract.objects.filter(valid_until__lt=today).update(is_archived=True)
    Contract.objects.filter(
        valid_from__lte=today, is_active=False,
    ).update(is_archived=True)
    FundingAllocation.objects.filter(end_date__lt=today).update(is_archived=True)
    FundingAllocation.objects.filter(
        start_date__lte=today, is_active=False,
    ).update(is_archived=True)


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0029_employee_is_external'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='is_archived',
            field=models.BooleanField(
                default=False,
                help_text='Moved to archive (ended or archived by hand). Upcoming contracts stay unarchived.',
                verbose_name='Archived',
            ),
        ),
        migrations.AddField(
            model_name='fundingallocation',
            name='is_archived',
            field=models.BooleanField(
                default=False,
                help_text='Moved to archive (ended or archived by hand). Upcoming allocations stay unarchived.',
                verbose_name='Archived',
            ),
        ),
        migrations.RunPython(mark_ended_as_archived, migrations.RunPython.noop),
    ]

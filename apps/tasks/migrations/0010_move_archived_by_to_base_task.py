# Combined migration to move archived_by from PurchaseOrderTask to base Task
# Remove from PO in state first, then add to base Task to avoid clash.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0004_contract_job_number'),
        ('tasks', '0009_fix_standardpurchaseitem_state'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='purchaseordertask',
            name='archived_by',
        ),
        migrations.AddField(
            model_name='task',
            name='archived_by',
            field=models.ManyToManyField(blank=True, related_name='archived_tasks', to='hr.employee', verbose_name='Archived by users'),
        ),
    ]



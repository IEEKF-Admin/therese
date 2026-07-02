# Merge parallel migration branches (production 0003_alter + repository 0013).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0003_alter_purchaseordertask_options_alter_task_options'),
        ('tasks', '0013_approval_permissions'),
    ]

    operations = []
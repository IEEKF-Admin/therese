from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0021_task_workflow_coordinators'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseordertask',
            name='is_quote_order',
            field=models.BooleanField(
                default=False,
                help_text='Quote-only variant: creator uploads a PDF instead of line items.',
                verbose_name='Order with Quote',
            ),
        ),
        migrations.AddField(
            model_name='purchaseordertask',
            name='quote_file',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='purchase_orders/quotes/%Y/%m/%d/',
                verbose_name='Quote',
            ),
        ),
        migrations.AlterField(
            model_name='purchaseordertask',
            name='supplier',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Supplier'),
        ),
    ]
# Generated manually - StandardPurchaseItem model

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0006_purchaseordertask_archived_by'),
        ('hr', '0001_initial'),  # Employee FK
    ]

    operations = [
        migrations.CreateModel(
            name='StandardPurchaseItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supplier', models.CharField(max_length=200)),
                ('product_name', models.CharField(max_length=255)),
                ('product_description', models.TextField(blank=True)),
                ('link_to_product', models.URLField(blank=True)),
                ('order_number', models.CharField(blank=True, max_length=50)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('image', models.BinaryField(blank=True, null=True)),
                ('image_filename', models.CharField(blank=True, max_length=255)),
                ('image_content_type', models.CharField(blank=True, max_length=100)),
                ('thumbnail', models.BinaryField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=models.PROTECT, related_name='created_standard_items', to='hr.employee')),
            ],
            options={
                'verbose_name': 'Standard Purchase Item',
                'verbose_name_plural': 'Standard Purchase Items',
                'ordering': ['supplier', 'product_name'],
            },
        ),
    ]


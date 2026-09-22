import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('hr', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='InventoryItemType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='Name')),
                ('prefix', models.CharField(help_text='Used for auto IDs, e.g. SM → SM-0001.', max_length=10, unique=True, verbose_name='ID prefix')),
                ('next_number', models.PositiveIntegerField(default=1, verbose_name='Next sequence number')),
            ],
            options={
                'verbose_name': 'Inventory item type',
                'verbose_name_plural': 'Inventory item types',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='InventoryItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('code', models.CharField(db_index=True, max_length=32, unique=True, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Name')),
                ('purchase_date', models.DateField(blank=True, null=True, verbose_name='Purchase date')),
                ('purchase_price', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Purchase price')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('current_holder', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inventory_items', to='hr.employee', verbose_name='Issued to')),
                ('item_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='inventory.inventoryitemtype', verbose_name='Item type')),
            ],
            options={
                'verbose_name': 'Inventory item',
                'verbose_name_plural': 'Inventory items',
                'ordering': ['code'],
                'permissions': [
                    ('view_own_inventory_items', 'Can view inventory items issued to self'),
                    ('view_all_inventory_items', 'Can view all inventory items'),
                    ('manage_inventory_items', 'Can manage inventory items'),
                ],
            },
        ),
        migrations.CreateModel(
            name='InventoryIssuance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('issued_at', models.DateTimeField(verbose_name='Issued at')),
                ('returned_at', models.DateTimeField(blank=True, null=True, verbose_name='Returned at')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_issuances', to='hr.employee', verbose_name='Employee')),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inventory_issuances_recorded', to='hr.employee', verbose_name='Issued by')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='issuances', to='inventory.inventoryitem', verbose_name='Item')),
                ('returned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inventory_returns_recorded', to='hr.employee', verbose_name='Returned by')),
            ],
            options={
                'verbose_name': 'Inventory issuance',
                'verbose_name_plural': 'Inventory issuances',
                'ordering': ['-issued_at', '-pk'],
            },
        ),
    ]

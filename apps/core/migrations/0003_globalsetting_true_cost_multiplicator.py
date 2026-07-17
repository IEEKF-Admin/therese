from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_stored_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsetting',
            name='true_cost_multiplicator',
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal('1.300'),
                help_text='Monthly costs = monthly salary × this factor (default 1.3).',
                max_digits=5,
                verbose_name='True-Cost Multiplicator',
            ),
        ),
    ]

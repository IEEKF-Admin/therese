from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_limitation_pdf_letterhead'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsetting',
            name='inventory_enabled',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Master switch. When off, inventory menus and pages are hidden. '
                    'Item types are configured on the Inventory tab.'
                ),
                verbose_name='Inventory module',
            ),
        ),
    ]

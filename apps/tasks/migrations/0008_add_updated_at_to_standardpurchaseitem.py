# Manually created - add missing updated_at column from BaseModel

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0007_standardpurchaseitem'),
    ]

    operations = [
        migrations.AddField(
            model_name='standardpurchaseitem',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Updated At'),
        ),
    ]


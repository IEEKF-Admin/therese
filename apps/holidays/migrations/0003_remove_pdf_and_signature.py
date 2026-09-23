from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('holidays', '0002_entitlement_breakdown'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='holidayprofile',
            name='signature',
        ),
        migrations.RemoveField(
            model_name='holidayrequest',
            name='pdf_file',
        ),
    ]

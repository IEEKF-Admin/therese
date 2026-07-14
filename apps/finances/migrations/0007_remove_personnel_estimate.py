from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0006_psp_cost_center_enhancements'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='costcenteryearestimate',
            name='personnel_estimate',
        ),
        migrations.RemoveField(
            model_name='wbselementyearestimate',
            name='personnel_estimate',
        ),
    ]
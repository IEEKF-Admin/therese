from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_globalsetting_irresponsible'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsetting',
            name='show_add_employee_on_reallocation',
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When enabled, the personnel reallocation create form shows a button "
                    "to create a new employee with the minimal required fields."
                ),
                verbose_name='Show “Add new Employee” on reallocation',
            ),
        ),
    ]

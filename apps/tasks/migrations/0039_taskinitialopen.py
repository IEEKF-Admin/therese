from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tasks', '0038_change_working_hours_task'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskInitialOpen',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('opened_at', models.DateTimeField(auto_now_add=True, verbose_name='Opened at')),
                ('task', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='initial_opens',
                    to='tasks.task',
                    verbose_name='Task',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='task_initial_opens',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='User',
                )),
            ],
            options={
                'verbose_name': 'Task initial open',
                'verbose_name_plural': 'Task initial opens',
            },
        ),
        migrations.AddConstraint(
            model_name='taskinitialopen',
            constraint=models.UniqueConstraint(
                fields=('user', 'task'),
                name='task_initial_open_user_task_uniq',
            ),
        ),
    ]

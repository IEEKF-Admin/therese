from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('checklists', '0004_editable_by_groups'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChecklistEditorArchive',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('archived_at', models.DateTimeField(auto_now_add=True, verbose_name='Archived at')),
                ('instance', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='editor_archives',
                    to='checklists.checklistinstance',
                    verbose_name='Instance',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='checklist_editor_archives',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='User',
                )),
            ],
            options={
                'verbose_name': 'Checklist Editor Archive',
                'verbose_name_plural': 'Checklist Editor Archives',
            },
        ),
        migrations.CreateModel(
            name='ChecklistEditorSeen',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('seen_at', models.DateTimeField(auto_now_add=True, verbose_name='Seen at')),
                ('instance', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='editor_seens',
                    to='checklists.checklistinstance',
                    verbose_name='Instance',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='checklist_editor_seens',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='User',
                )),
            ],
            options={
                'verbose_name': 'Checklist Editor Seen',
                'verbose_name_plural': 'Checklist Editor Seens',
            },
        ),
        migrations.AddConstraint(
            model_name='checklisteditorarchive',
            constraint=models.UniqueConstraint(
                fields=('user', 'instance'),
                name='checklist_editor_archive_user_instance_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='checklisteditorseen',
            constraint=models.UniqueConstraint(
                fields=('user', 'instance'),
                name='checklist_editor_seen_user_instance_uniq',
            ),
        ),
    ]

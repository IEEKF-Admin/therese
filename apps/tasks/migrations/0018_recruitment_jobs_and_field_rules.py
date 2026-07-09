# Generated manually for recruitment job configuration

import django.db.models.deletion
from django.db import migrations, models


def ensure_default_job_and_assign(apps, schema_editor):
    RecruitmentJob = apps.get_model('tasks', 'RecruitmentJob')
    PersonnelRecruitmentTask = apps.get_model('tasks', 'PersonnelRecruitmentTask')
    default_job, _ = RecruitmentJob.objects.get_or_create(
        name='Default Job',
        defaults={'is_active': True},
    )
    PersonnelRecruitmentTask.objects.filter(job_id__isnull=True).update(job_id=default_job.pk)


def migrate_degree_document_type(apps, schema_editor):
    EmployeeDocumentVersion = apps.get_model('hr', 'EmployeeDocumentVersion')
    EmployeeDocumentVersion.objects.filter(document_type='measles_proof').update(
        document_type='latest_degree_certificate',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0017_recruitment_plan_position_optional'),
        ('hr', '0008_workgroup_auth_group'),
    ]

    operations = [
        migrations.CreateModel(
            name='RecruitmentJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('name', models.CharField(max_length=200, unique=True, verbose_name='Job Name')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
            ],
            options={
                'verbose_name': 'Recruitment Job',
                'verbose_name_plural': 'Recruitment Jobs',
                'ordering': ['name'],
                'permissions': [('manage_recruitment_job', 'Can manage recruitment jobs')],
            },
        ),
        migrations.CreateModel(
            name='LimitationReason',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('title', models.CharField(max_length=200, verbose_name='Title')),
                ('text', models.TextField(verbose_name='Limitation Reason Text')),
                ('applies_to_all_jobs', models.BooleanField(default=False, verbose_name='Applies to All Jobs')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
                ('jobs', models.ManyToManyField(blank=True, related_name='limitation_reasons', to='tasks.recruitmentjob', verbose_name='Associated Jobs')),
            ],
            options={
                'verbose_name': 'Limitation Reason',
                'verbose_name_plural': 'Limitation Reasons',
                'ordering': ['title'],
                'permissions': [('manage_limitation_reason', 'Can manage limitation reasons')],
            },
        ),
        migrations.CreateModel(
            name='RecruitmentJobFieldRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('field_key', models.CharField(max_length=50, verbose_name='Field Key')),
                ('visibility_mode', models.CharField(choices=[('always', 'Always visible'), ('never', 'Never visible'), ('when_duration', 'Visible when duration matches')], default='always', max_length=20, verbose_name='Visibility')),
                ('visibility_duration_operator', models.CharField(blank=True, choices=[('lt', 'Less than'), ('lte', 'Less than or equal'), ('gt', 'Greater than'), ('gte', 'Greater than or equal'), ('eq', 'Equal to')], max_length=5, verbose_name='Visibility Duration Operator')),
                ('visibility_duration_months', models.PositiveIntegerField(blank=True, null=True, verbose_name='Visibility Duration (months)')),
                ('required_mode', models.CharField(choices=[('never', 'Optional'), ('always', 'Always required'), ('when_duration', 'Required when duration matches')], default='never', max_length=20, verbose_name='Required')),
                ('required_duration_operator', models.CharField(blank=True, choices=[('lt', 'Less than'), ('lte', 'Less than or equal'), ('gt', 'Greater than'), ('gte', 'Greater than or equal'), ('eq', 'Equal to')], max_length=5, verbose_name='Required Duration Operator')),
                ('required_duration_months', models.PositiveIntegerField(blank=True, null=True, verbose_name='Required Duration (months)')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='field_rules', to='tasks.recruitmentjob', verbose_name='Job')),
            ],
            options={
                'verbose_name': 'Recruitment Job Field Rule',
                'verbose_name_plural': 'Recruitment Job Field Rules',
                'ordering': ['field_key'],
                'unique_together': {('job', 'field_key')},
            },
        ),
        migrations.AddField(
            model_name='personnelrecruitmenttask',
            name='limitation_reason',
            field=models.TextField(blank=True, verbose_name='Limitation Reason'),
        ),
        migrations.AddField(
            model_name='personnelrecruitmenttask',
            name='job',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='recruitment_tasks',
                to='tasks.recruitmentjob',
                verbose_name='Job',
            ),
        ),
        migrations.AlterField(
            model_name='personnelrecruitmenttask',
            name='application_file',
            field=models.FileField(blank=True, null=True, upload_to='recruitment_tasks/application/', verbose_name='Application'),
        ),
        migrations.AlterField(
            model_name='personnelrecruitmenttask',
            name='private_phone_number',
            field=models.CharField(blank=True, max_length=30, verbose_name='Private Phone'),
        ),
        migrations.RenameField(
            model_name='personnelrecruitmenttask',
            old_name='measles_proof_file',
            new_name='latest_degree_certificate_file',
        ),
        migrations.AlterField(
            model_name='personnelrecruitmenttask',
            name='latest_degree_certificate_file',
            field=models.FileField(upload_to='recruitment_tasks/degree_certificates/', verbose_name='Latest Degree Certificate'),
        ),
        migrations.RunPython(ensure_default_job_and_assign, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='personnelrecruitmenttask',
            name='job_title',
        ),
        migrations.AlterField(
            model_name='personnelrecruitmenttask',
            name='job',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='recruitment_tasks', to='tasks.recruitmentjob', verbose_name='Job'),
        ),
        migrations.AlterField(
            model_name='personnelrecruitmenttask',
            name='valid_until',
            field=models.DateField(verbose_name='Contract End Date'),
        ),
        migrations.RunPython(migrate_degree_document_type, migrations.RunPython.noop),
    ]
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0036_smtp_and_sympa'),
    ]

    operations = [
        migrations.CreateModel(
            name='WordPressSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('name', models.CharField(max_length=120, verbose_name='Name')),
                ('url', models.URLField(blank=True, default='', verbose_name='URL')),
                ('username', models.CharField(blank=True, default='', max_length=150, verbose_name='WordPress user')),
                ('application_password', models.CharField(
                    blank=True,
                    default='',
                    help_text='Leave blank to keep the saved password. Not shown again after saving.',
                    max_length=255,
                    verbose_name='Application password',
                )),
                ('workgroups', models.ManyToManyField(
                    blank=True,
                    related_name='wordpress_sites',
                    to='hr.workgroup',
                    verbose_name='Workgroups',
                )),
            ],
            options={
                'verbose_name': 'WordPress site',
                'verbose_name_plural': 'WordPress sites',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='EmployeeWordPressEnrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('posttitle', models.CharField(blank=True, default='', max_length=255)),
                ('wp_post_id', models.PositiveIntegerField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('published', 'Shared'),
                        ('unpublished', 'Unpublished'),
                        ('error', 'Error'),
                    ],
                    db_index=True,
                    default='unpublished',
                    max_length=20,
                )),
                ('last_source', models.JSONField(blank=True, default=dict)),
                ('last_sent', models.JSONField(blank=True, default=dict)),
                ('detail', models.TextField(blank=True, default='')),
                ('needs_attention', models.BooleanField(db_index=True, default=False)),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('employee', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='wordpress_enrollments',
                    to='hr.employee',
                    verbose_name='Employee',
                )),
                ('site', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='enrollments',
                    to='hr.wordpresssite',
                    verbose_name='WordPress site',
                )),
            ],
            options={
                'verbose_name': 'Employee WordPress enrollment',
                'verbose_name_plural': 'Employee WordPress enrollments',
                'ordering': ['employee__last_name', 'employee__first_name', 'site__name'],
            },
        ),
        migrations.AddConstraint(
            model_name='employeewordpressenrollment',
            constraint=models.UniqueConstraint(
                fields=('employee', 'site'),
                name='hr_wp_enrollment_employee_site',
            ),
        ),
    ]

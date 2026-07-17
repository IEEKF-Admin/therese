from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models
import django.db.models.deletion


def convert_recruitment_funding(apps, schema_editor):
    RecruitmentFundingAllocation = apps.get_model('tasks', 'RecruitmentFundingAllocation')
    PersonnelRecruitmentTask = apps.get_model('tasks', 'PersonnelRecruitmentTask')
    GlobalSetting = apps.get_model('core', 'GlobalSetting')

    try:
        default_hours = GlobalSetting.objects.get(pk=1).default_weekly_hours
    except GlobalSetting.DoesNotExist:
        default_hours = Decimal('39.00')
    if not default_hours or default_hours <= 0:
        default_hours = Decimal('39.00')

    for allocation in RecruitmentFundingAllocation.objects.all().iterator():
        hours = allocation.weekly_hours_allocated
        task = PersonnelRecruitmentTask.objects.filter(pk=allocation.recruitment_task_id).first()
        weekly = default_hours
        if task and getattr(task, 'weekly_hours', None):
            weekly = task.weekly_hours
        if weekly and weekly > 0 and hours is not None:
            percentage = (Decimal(hours) / Decimal(weekly) * Decimal('100')).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )
        else:
            percentage = Decimal(hours or 0)

        plan_position = ''
        if task and getattr(task, 'plan_position_number', ''):
            plan_position = task.plan_position_number

        allocation.workhours_percentage = percentage
        allocation.plan_position_number = plan_position or ''
        allocation.save(update_fields=['workhours_percentage', 'plan_position_number'])


def migrate_reallocation_funding(apps, schema_editor):
    PersonnelReallocationTask = apps.get_model('tasks', 'PersonnelReallocationTask')
    ReallocationFundingAllocation = apps.get_model('tasks', 'ReallocationFundingAllocation')

    for task in PersonnelReallocationTask.objects.all().iterator():
        if not task.target_wbs_id:
            continue
        ReallocationFundingAllocation.objects.create(
            reallocation_task_id=task.pk,
            wbs_element_id=task.target_wbs_id,
            cost_center_id=None,
            workhours_percentage=Decimal('100.00'),
            plan_position_number=task.plan_position_number or '',
            notes='',
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_globalsetting_true_cost_multiplicator'),
        ('finances', '0007_remove_personnel_estimate'),
        ('tasks', '0027_funding_allocation_cost_center'),
    ]

    operations = [
        migrations.AddField(
            model_name='personnelrecruitmenttask',
            name='weekly_hours',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name='Weekly Working Hours',
            ),
        ),
        migrations.AddField(
            model_name='recruitmentfundingallocation',
            name='workhours_percentage',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('100.00'),
                max_digits=6,
                verbose_name='Percentage of Workhours',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='recruitmentfundingallocation',
            name='plan_position_number',
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name='Plan Position Number',
            ),
        ),
        migrations.RunPython(convert_recruitment_funding, noop_reverse),
        migrations.RemoveField(
            model_name='recruitmentfundingallocation',
            name='weekly_hours_allocated',
        ),
        migrations.RemoveField(
            model_name='personnelrecruitmenttask',
            name='plan_position_number',
        ),
        migrations.CreateModel(
            name='ReallocationFundingAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('workhours_percentage', models.DecimalField(
                    decimal_places=2,
                    max_digits=6,
                    verbose_name='Percentage of Workhours',
                )),
                ('plan_position_number', models.CharField(
                    blank=True,
                    max_length=50,
                    verbose_name='Plan Position Number',
                )),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('cost_center', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='reallocation_funding_allocations',
                    to='finances.costcenter',
                    verbose_name='Cost Center',
                )),
                ('reallocation_task', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='funding_allocations',
                    to='tasks.personnelreallocationtask',
                    verbose_name='Reallocation Task',
                )),
                ('wbs_element', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    to='finances.wbselement',
                    verbose_name='WBS Element',
                )),
            ],
            options={
                'verbose_name': 'Reallocation Funding Allocation',
                'verbose_name_plural': 'Reallocation Funding Allocations',
                'ordering': ['id'],
            },
        ),
        migrations.AddConstraint(
            model_name='reallocationfundingallocation',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(('wbs_element__isnull', False), ('cost_center__isnull', True))
                    | models.Q(('wbs_element__isnull', True), ('cost_center__isnull', False))
                ),
                name='reallocation_funding_allocation_one_target',
            ),
        ),
        migrations.RunPython(migrate_reallocation_funding, noop_reverse),
        migrations.RemoveField(
            model_name='personnelreallocationtask',
            name='target_wbs',
        ),
        migrations.RemoveField(
            model_name='personnelreallocationtask',
            name='plan_position_number',
        ),
    ]

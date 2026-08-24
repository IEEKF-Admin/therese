from datetime import date

from django.test import TestCase

from apps.tasks.models import LimitationReason, RecruitmentJob, RecruitmentJobFieldRule
from apps.tasks.recruitment_config import (
    VisibilityMode,
    RequiredMode,
    DurationOperator,
    contract_duration_months,
    get_effective_rules_for_job,
    is_field_required,
    is_field_visible,
    limitation_reasons_for_job,
    serialize_all_job_rules,
    visible_recruitment_jobs,
)


class ContractDurationTests(TestCase):
    def test_full_calendar_months(self):
        self.assertEqual(
            contract_duration_months(date(2026, 1, 1), date(2026, 3, 31)),
            3,
        )
        self.assertEqual(
            contract_duration_months(date(2026, 1, 15), date(2026, 3, 14)),
            2,
        )


class JobFieldRuleTests(TestCase):
    def setUp(self):
        self.job = RecruitmentJob.objects.create(name='Praktikant')

    def test_visibility_and_required_with_duration_threshold(self):
        RecruitmentJobFieldRule.objects.create(
            job=self.job,
            field_key='limitation_reason',
            visibility_mode=VisibilityMode.ALWAYS,
            required_mode=RequiredMode.WHEN_DURATION,
            required_duration_operator=DurationOperator.LT,
            required_duration_months=3,
        )
        rule = self.job.field_rules.get(field_key='limitation_reason')
        self.assertTrue(is_field_visible(rule, 2))
        self.assertTrue(is_field_required(rule, 2, 'limitation_reason'))
        self.assertFalse(is_field_required(rule, 4, 'limitation_reason'))


class RecruitmentJobSalaryTests(TestCase):
    def test_estimated_salary_from_current_payscale(self):
        from apps.finances.models import PayScale
        from datetime import date

        PayScale.objects.create(
            pay_scale_group='E13',
            experience_level=3,
            monthly_salary='4500.00',
            effective_as_of=date(2026, 1, 1),
        )
        job = RecruitmentJob.objects.create(
            name='Scientist',
            pay_scale_group='E13',
            experience_level=3,
        )
        self.assertEqual(job.get_estimated_monthly_salary(), 4500.00)

    def test_estimated_salary_missing_returns_none(self):
        job = RecruitmentJob.objects.create(name='Intern')
        self.assertIsNone(job.get_estimated_monthly_salary())

    def test_fixed_estimated_monthly_salary_on_job(self):
        from decimal import Decimal

        job = RecruitmentJob.objects.create(
            name='Postdoc fixed',
            estimated_monthly_salary=Decimal('3200.00'),
        )
        self.assertEqual(job.get_estimated_monthly_salary(), Decimal('3200.00'))

    def test_job_rejects_tvl_and_estimate_together(self):
        from decimal import Decimal
        from django.core.exceptions import ValidationError

        job = RecruitmentJob(
            name='Conflict',
            pay_scale_group='E13',
            experience_level=1,
            estimated_monthly_salary=Decimal('1000.00'),
        )
        with self.assertRaises(ValidationError):
            job.full_clean()

    def test_task_monthly_costs_pro_rata_weekly_hours(self):
        from datetime import date
        from decimal import Decimal

        from apps.core.models import GlobalSetting
        from apps.tasks.models import PersonnelRecruitmentTask

        GlobalSetting.objects.filter(pk=1).delete()
        GlobalSetting.objects.create(
            pk=1,
            default_weekly_hours=Decimal('40.00'),
            true_cost_multiplicator=Decimal('1.300'),
        )
        job = RecruitmentJob.objects.create(
            name='Half time job',
            estimated_monthly_salary=Decimal('4000.00'),
        )
        task = PersonnelRecruitmentTask(
            job=job,
            monthly_salary=Decimal('4000.00'),
            weekly_hours=Decimal('20.00'),
            first_name='A',
            last_name='B',
            street='S',
            house_number='1',
            postal_code='1',
            city='C',
            date_of_birth=date(1990, 1, 1),
            country_of_origin='DE',
            place_of_birth='X',
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
        )
        # 4000 * 0.5 * 1.3 = 2600
        self.assertEqual(task.get_estimated_monthly_costs(), Decimal('2600.00'))
        task.weekly_hours = None
        # 4000 * 1.0 * 1.3 = 5200
        self.assertEqual(task.get_estimated_monthly_costs(), Decimal('5200.00'))


class StandardJobInheritanceTests(TestCase):
    def test_standard_job_exists_and_is_hidden(self):
        from apps.tasks.models import RecruitmentJob

        standard = RecruitmentJob.objects.get(is_standard=True)
        self.assertEqual(standard.name, 'Standard')
        self.assertNotIn(standard, list(visible_recruitment_jobs()))
        self.assertNotIn(str(standard.pk), serialize_all_job_rules())

    def test_unset_job_inherits_limitation_when_end_date_set(self):
        from apps.tasks.models import RecruitmentJob

        job = RecruitmentJob.objects.create(name='Inherited job')
        rules = get_effective_rules_for_job(job)
        limitation = rules['limitation_reason']
        self.assertEqual(limitation.visibility_mode, VisibilityMode.WHEN_FIELD_SET)
        self.assertEqual(limitation.visibility_trigger_field, 'valid_until')
        self.assertFalse(is_field_visible(limitation, None, field_values={'valid_until': None}))
        self.assertTrue(is_field_visible(
            limitation, None, field_values={'valid_until': date(2026, 12, 31)},
        ))

    def test_job_override_beats_standard(self):
        from apps.tasks.models import RecruitmentJob, RecruitmentJobFieldRule

        job = RecruitmentJob.objects.create(name='Override job')
        RecruitmentJobFieldRule.objects.create(
            job=job,
            field_key='limitation_reason',
            visibility_mode=VisibilityMode.NEVER,
            required_mode=RequiredMode.NEVER,
        )
        rules = get_effective_rules_for_job(job)
        self.assertEqual(rules['limitation_reason'].visibility_mode, VisibilityMode.NEVER)
        self.assertFalse(is_field_visible(rules['limitation_reason'], None, field_values={
            'valid_until': date(2026, 12, 31),
        }))


class LimitationReasonFilterTests(TestCase):
    def setUp(self):
        self.job_a = RecruitmentJob.objects.create(name='Job A')
        self.job_b = RecruitmentJob.objects.create(name='Job B')
        self.reason_all = LimitationReason.objects.create(
            title='All jobs',
            text='Applies everywhere',
            applies_to_all_jobs=True,
        )
        self.reason_specific = LimitationReason.objects.create(
            title='Only A',
            text='Only for A',
            applies_to_all_jobs=False,
        )
        self.reason_specific.jobs.add(self.job_a)

    def test_filters_by_associated_jobs(self):
        titles = {item['title'] for item in limitation_reasons_for_job(self.job_a.pk)}
        self.assertIn('All jobs', titles)
        self.assertIn('Only A', titles)

        titles_b = {item['title'] for item in limitation_reasons_for_job(self.job_b.pk)}
        self.assertIn('All jobs', titles_b)
        self.assertNotIn('Only A', titles_b)
from datetime import date

from django.test import TestCase

from apps.tasks.models import LimitationReason, RecruitmentJob, RecruitmentJobFieldRule
from apps.tasks.recruitment_config import (
    VisibilityMode,
    RequiredMode,
    DurationOperator,
    contract_duration_months,
    is_field_required,
    is_field_visible,
    limitation_reasons_for_job,
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
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.hr.funding_coverage import (
    allocation_counts_toward_coverage,
    coverage_error_message,
    periods_not_exactly_100,
)
from apps.hr.views.employee_form_helpers import validate_active_contract_funding_totals


class FundingCoverageTests(TestCase):
    def test_sequential_full_allocations_are_ok(self):
        rows = [
            (date(2026, 1, 1), date(2026, 9, 30), Decimal('100')),
            (date(2026, 10, 1), date(2026, 12, 31), Decimal('100')),
        ]
        self.assertEqual(
            periods_not_exactly_100(date(2026, 1, 1), date(2026, 12, 31), rows),
            [],
        )
        self.assertIsNone(
            coverage_error_message('01.01.2026', date(2026, 1, 1), date(2026, 12, 31), rows),
        )

    def test_overlapping_full_allocations_fail(self):
        rows = [
            (date(2026, 1, 1), date(2026, 12, 31), Decimal('100')),
            (date(2026, 10, 1), date(2026, 12, 31), Decimal('100')),
        ]
        bad = periods_not_exactly_100(date(2026, 1, 1), date(2026, 12, 31), rows)
        self.assertTrue(bad)
        self.assertEqual(bad[-1][2], Decimal('200.00'))

    def test_gap_between_allocations_fails(self):
        rows = [
            (date(2026, 1, 1), date(2026, 9, 30), Decimal('100')),
            (date(2026, 11, 1), date(2026, 12, 31), Decimal('100')),
        ]
        bad = periods_not_exactly_100(date(2026, 1, 1), date(2026, 12, 31), rows)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0][0], date(2026, 10, 1))
        self.assertEqual(bad[0][1], date(2026, 10, 31))
        self.assertEqual(bad[0][2], Decimal('0.00'))

    def test_open_ended_followup_is_ok(self):
        rows = [
            (date(2026, 1, 1), date(2026, 9, 30), Decimal('100')),
            (date(2026, 10, 1), None, Decimal('100')),
        ]
        self.assertEqual(
            periods_not_exactly_100(date(2026, 1, 1), None, rows),
            [],
        )

    def test_split_percentages_same_period_ok(self):
        rows = [
            (date(2026, 1, 1), None, Decimal('40')),
            (date(2026, 1, 1), None, Decimal('60')),
        ]
        self.assertEqual(
            periods_not_exactly_100(date(2026, 1, 1), None, rows),
            [],
        )

    def test_upcoming_inactive_allocation_counts(self):
        self.assertTrue(
            allocation_counts_toward_coverage(
                date(2028, 5, 1), None, is_active=False,
            )
        )

    def test_deactivated_current_allocation_does_not_count(self):
        self.assertFalse(
            allocation_counts_toward_coverage(
                date(2024, 5, 1), date(2028, 4, 30), is_active=False,
            )
        )

    def test_archived_allocation_does_not_count(self):
        self.assertFalse(
            allocation_counts_toward_coverage(
                date(2028, 5, 1), None, is_active=False, is_archived=True,
            )
        )


class _Form:
    def __init__(self, **cleaned):
        self.cleaned_data = cleaned


class _Formset:
    def __init__(self, forms):
        self.forms = forms

    def is_valid(self):
        return True


class ActiveContractFundingTotalsTests(TestCase):
    def test_upcoming_followup_covers_open_contract(self):
        """Braganza case: current 100% until 30.04.2028, upcoming 100% from 01.05.2028."""
        cform = _Form(
            DELETE=False,
            is_active=True,
            valid_from=date(2024, 5, 1),
            valid_until=None,
        )
        fa_fs = _Formset([
            _Form(
                DELETE=False,
                is_active=True,
                is_archived=False,
                start_date=date(2024, 5, 1),
                end_date=date(2028, 4, 30),
                workhours_percentage=Decimal('100'),
            ),
            _Form(
                DELETE=False,
                is_active=False,
                is_archived=False,
                start_date=date(2028, 5, 1),
                end_date=None,
                workhours_percentage=Decimal('100'),
            ),
        ])
        self.assertEqual(
            validate_active_contract_funding_totals(None, [(0, cform, fa_fs)]),
            [],
        )

    def test_inactive_upcoming_ignored_used_to_report_zero(self):
        cform = _Form(
            DELETE=False,
            is_active=True,
            valid_from=date(2024, 5, 1),
            valid_until=None,
        )
        fa_fs = _Formset([
            _Form(
                DELETE=False,
                is_active=True,
                is_archived=False,
                start_date=date(2024, 5, 1),
                end_date=date(2028, 4, 30),
                workhours_percentage=Decimal('100'),
            ),
        ])
        errors = validate_active_contract_funding_totals(None, [(0, cform, fa_fs)])
        self.assertEqual(len(errors), 1)
        self.assertIn('01.05.2028 onward: 0.00%', errors[0])

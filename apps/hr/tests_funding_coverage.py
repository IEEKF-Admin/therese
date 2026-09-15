from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.hr.funding_coverage import coverage_error_message, periods_not_exactly_100


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

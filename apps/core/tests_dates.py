from datetime import date

from django.test import TestCase

from apps.core.dates import EuropeanDateField, expand_two_digit_year
from apps.hr.forms import ContractForm, FundingAllocationForm


class TwoDigitYearDateTests(TestCase):
    def test_expand_two_digit_year(self):
        self.assertEqual(expand_two_digit_year('01.01.28'), '01.01.2028')
        self.assertEqual(expand_two_digit_year('1.1.28'), '01.01.2028')
        self.assertEqual(expand_two_digit_year('01.01.2026'), '01.01.2026')
        self.assertEqual(expand_two_digit_year(''), '')

    def test_european_date_field_uses_20xx(self):
        field = EuropeanDateField()
        self.assertEqual(field.clean('01.01.28'), date(2028, 1, 1))
        self.assertEqual(field.clean('31.12.99'), date(2099, 12, 31))
        self.assertEqual(field.clean('15.06.2027'), date(2027, 6, 15))

    def test_contract_and_funding_forms_accept_two_digit_year(self):
        contract = ContractForm(data={
            'weekly_hours': '39.000',
            'valid_from': '01.01.28',
            'valid_until': '31.12.29',
        })
        self.assertTrue(contract.is_valid(), contract.errors)
        self.assertEqual(contract.cleaned_data['valid_from'], date(2028, 1, 1))
        self.assertEqual(contract.cleaned_data['valid_until'], date(2029, 12, 31))

        funding = FundingAllocationForm(data={
            'funding_source': '',
            'workhours_percentage': '100',
            'start_date': '01.03.28',
            'end_date': '30.09.28',
        })
        # funding_source required — still check date parsing independently
        self.assertEqual(funding.fields['start_date'].clean('01.03.28'), date(2028, 3, 1))
        self.assertEqual(funding.fields['end_date'].clean('30.09.28'), date(2028, 9, 30))

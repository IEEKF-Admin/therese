"""Default vacation-day table (weekdays per week × contract months in the year)."""

from decimal import Decimal

# months 12 → 1
DEFAULT_RATES = {
    5: [Decimal('30'), Decimal('27.5'), Decimal('25'), Decimal('22.5'), Decimal('20'),
        Decimal('17.5'), Decimal('15'), Decimal('12.5'), Decimal('10'), Decimal('7.5'),
        Decimal('5'), Decimal('2.5')],
    4: [Decimal('24'), Decimal('22'), Decimal('20'), Decimal('18'), Decimal('16'),
        Decimal('14'), Decimal('12'), Decimal('10'), Decimal('8'), Decimal('6'),
        Decimal('4'), Decimal('2')],
    3: [Decimal('18'), Decimal('16.5'), Decimal('15'), Decimal('13.5'), Decimal('12'),
        Decimal('10.5'), Decimal('9'), Decimal('7.5'), Decimal('6'), Decimal('4.5'),
        Decimal('3'), Decimal('1.5')],
    2: [Decimal('12'), Decimal('11'), Decimal('10'), Decimal('9'), Decimal('8'),
        Decimal('7'), Decimal('6'), Decimal('5'), Decimal('4'), Decimal('3'),
        Decimal('2'), Decimal('1')],
    1: [Decimal('6'), Decimal('5.5'), Decimal('5'), Decimal('4.5'), Decimal('4'),
        Decimal('3.5'), Decimal('3'), Decimal('2.5'), Decimal('2'), Decimal('1.5'),
        Decimal('1'), Decimal('0.5')],
}


def months_to_index(contract_months):
    months = max(1, min(12, int(contract_months)))
    return 12 - months

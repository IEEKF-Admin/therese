"""Time-aware funding allocation coverage: exactly 100% on every day."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

HUNDRED = Decimal('100.00')


def _q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _format_day(value) -> str:
    if value is None:
        return 'open-ended'
    return value.strftime('%d.%m.%Y')


def iter_funding_intervals(contract_start, contract_end, rows):
    """
    Yield (interval_start, interval_end, total) for constant-sum slices.

    ``interval_end`` is inclusive; ``None`` means the slice is open-ended.
    ``rows``: iterable of (start_date, end_date|None, percentage).
    """
    if contract_start is None:
        return

    deltas = defaultdict(lambda: Decimal('0'))
    for start, end, pct in rows:
        if start is None or pct is None:
            continue
        pct = Decimal(pct)
        clip_start = start if start > contract_start else contract_start
        if contract_end is not None:
            raw_end = end if end is not None else contract_end
            clip_end = raw_end if raw_end < contract_end else contract_end
        else:
            clip_end = end
        if clip_end is not None and clip_start > clip_end:
            continue
        deltas[clip_start] += pct
        if clip_end is not None:
            deltas[clip_end + timedelta(days=1)] -= pct

    points = set(deltas)
    points.add(contract_start)
    if contract_end is not None:
        points.add(contract_end + timedelta(days=1))
    ordered = sorted(points)

    running = Decimal('0')
    prev = None
    for point in ordered:
        if prev is not None:
            seg_start = prev
            seg_end = point - timedelta(days=1)
            check_start = seg_start if seg_start > contract_start else contract_start
            if contract_end is not None:
                check_end = seg_end if seg_end < contract_end else contract_end
            else:
                check_end = seg_end
            if check_start <= check_end:
                yield check_start, check_end, _q2(running)
        running += deltas[point]
        prev = point

    if contract_end is None and prev is not None:
        yield prev, None, _q2(running)


def periods_not_exactly_100(contract_start, contract_end, rows):
    return [
        (start, end, total)
        for start, end, total in iter_funding_intervals(contract_start, contract_end, rows)
        if total != HUNDRED
    ]


def coverage_error_message(contract_label, contract_start, contract_end, rows) -> str | None:
    bad = periods_not_exactly_100(contract_start, contract_end, rows)
    if not bad:
        return None
    bits = []
    for start, end, total in bad[:3]:
        if end is None:
            span = f'{_format_day(start)} onward'
        elif start == end:
            span = _format_day(start)
        else:
            span = f'{_format_day(start)}–{_format_day(end)}'
        bits.append(f'{span}: {total}%')
    extra = f' (+{len(bad) - 3} more)' if len(bad) > 3 else ''
    return (
        f'Active funding allocations on the active contract ({contract_label}) '
        f'must sum to exactly 100% on every day ({"; ".join(bits)}{extra}).'
    )

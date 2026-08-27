"""German public holidays (nationwide + Bundesland)."""

from datetime import date, timedelta

FEDERAL_STATES = [
    ('BW', 'Baden-Württemberg'),
    ('BY', 'Bavaria'),
    ('BE', 'Berlin'),
    ('BB', 'Brandenburg'),
    ('HB', 'Bremen'),
    ('HH', 'Hamburg'),
    ('HE', 'Hesse'),
    ('MV', 'Mecklenburg-Vorpommern'),
    ('NI', 'Lower Saxony'),
    ('NW', 'North Rhine-Westphalia'),
    ('RP', 'Rhineland-Palatinate'),
    ('SL', 'Saarland'),
    ('SN', 'Saxony'),
    ('ST', 'Saxony-Anhalt'),
    ('SH', 'Schleswig-Holstein'),
    ('TH', 'Thuringia'),
]


def easter_sunday(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return date(year, month, day + 1)


def public_holidays_for_year(year, state_code=''):
    """Return {date: name_en} for nationwide + selected state holidays."""
    easter = easter_sunday(year)
    days = {
        date(year, 1, 1): 'New Year',
        easter - timedelta(days=2): 'Good Friday',
        easter + timedelta(days=1): 'Easter Monday',
        date(year, 5, 1): 'Labour Day',
        easter + timedelta(days=39): 'Ascension Day',
        easter + timedelta(days=50): 'Whit Monday',
        date(year, 10, 3): 'German Unity Day',
        date(year, 12, 25): 'Christmas Day',
        date(year, 12, 26): 'Boxing Day',
    }
    state = (state_code or '').upper()
    epiphany = date(year, 1, 6)
    corpus = easter + timedelta(days=60)
    assumption = date(year, 8, 15)
    reformation = date(year, 10, 31)
    all_saints = date(year, 11, 1)
    womens_day = date(year, 3, 8)
    world_childrens = date(year, 9, 20)

    if state in {'BW', 'BY', 'ST'}:
        days[epiphany] = 'Epiphany'
    if state in {'BW', 'BY', 'HE', 'NW', 'RP', 'SL'}:
        days[corpus] = 'Corpus Christi'
    if state in {'BY', 'SL'}:
        days[assumption] = 'Assumption Day'
    if state in {'BB', 'HB', 'HH', 'MV', 'NI', 'SH', 'SN', 'ST', 'TH'}:
        days[reformation] = 'Reformation Day'
    if state in {'BW', 'BY', 'NW', 'RP', 'SL'}:
        days[all_saints] = 'All Saints’ Day'
    if state in {'BE', 'MV'}:
        days[womens_day] = 'International Women’s Day'
    if state == 'TH':
        days[world_childrens] = 'World Children’s Day'
    if state == 'SN':
        # Buß- und Bettag: Wednesday before 23 November
        nov23 = date(year, 11, 23)
        days[nov23 - timedelta(days=(nov23.weekday() - 2) % 7)] = 'Repentance Day'
    return days

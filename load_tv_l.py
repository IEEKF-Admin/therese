import os
import django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings')
django.setup()

from apps.employees.models import PayScale

# TV-L 2026 Daten (gültig ab 01.04.2026)
data = [
    # Entgeltgruppe, Stufe, Monatsgehalt, gültig_ab
    ('E 1', 1, 2365.47, date(2026, 4, 1)),
    ('E 2', 1, 2550.12, date(2026, 4, 1)),
    ('E 3', 1, 2680.35, date(2026, 4, 1)),
    ('E 4', 1, 2805.68, date(2026, 4, 1)),
    ('E 5', 1, 2950.25, date(2026, 4, 1)),
    ('E 6', 1, 3105.78, date(2026, 4, 1)),
    ('E 7', 1, 3250.45, date(2026, 4, 1)),
    ('E 8', 1, 3420.90, date(2026, 4, 1)),
    ('E 9a', 1, 3580.15, date(2026, 4, 1)),
    ('E 9b', 1, 3750.80, date(2026, 4, 1)),
    ('E 9c', 1, 3950.25, date(2026, 4, 1)),
    ('E 10', 1, 4150.60, date(2026, 4, 1)),
    ('E 11', 1, 4350.95, date(2026, 4, 1)),
    ('E 12', 1, 4600.30, date(2026, 4, 1)),
    ('E 13', 1, 4759.37, date(2026, 4, 1)),
    ('E 13', 2, 5106.09, date(2026, 4, 1)),
    ('E 13', 3, 5366.89, date(2026, 4, 1)),
    ('E 13', 4, 5873.56, date(2026, 4, 1)),
    ('E 13', 5, 6573.97, date(2026, 4, 1)),
    ('E 13', 6, 6764.69, date(2026, 4, 1)),
    ('E 14', 1, 5143.59, date(2026, 4, 1)),
    ('E 14', 2, 5515.90, date(2026, 4, 1)),
    ('E 14', 3, 5821.41, date(2026, 4, 1)),
    ('E 14', 4, 6283.38, date(2026, 4, 1)),
    ('E 14', 5, 6991.23, date(2026, 4, 1)),
    ('E 14', 6, 7194.48, date(2026, 4, 1)),
    ('E 15', 1, 5658.38, date(2026, 4, 1)),
    ('E 15', 2, 6067.30, date(2026, 4, 1)),
    ('E 15', 3, 6283.38, date(2026, 4, 1)),
    ('E 15', 4, 7050.89, date(2026, 4, 1)),
    ('E 15', 5, 7632.07, date(2026, 4, 1)),
    ('E 15', 6, 7854.52, date(2026, 4, 1)),
    ('E 15Ü', 1, 6857.14, date(2026, 4, 1)),
    ('E 15Ü', 2, 7587.33, date(2026, 4, 1)),
    ('E 15Ü', 3, 8280.33, date(2026, 4, 1)),
    ('E 15Ü', 4, 8734.83, date(2026, 4, 1)),
    ('E 15Ü', 5, 8846.64, date(2026, 4, 1)),
]

for group, level, salary, effective_date in data:
    PayScale.objects.update_or_create(
        pay_scale_group=group,
        experience_level=level,
        effective_as_of=effective_date,
        defaults={'monthly_salary': salary}
    )

print(f"{len(data)} TV-L Datensätze für 2026 erfolgreich in die Datenbank geladen!")
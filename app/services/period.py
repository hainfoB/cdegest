"""Année professionnelle : de septembre à août (mois de début paramétrable)."""
from datetime import date

START_MONTH = 9


def training_year(d=None):
    """(label, start, end, quarter) — ex. ('2026-2027', 2026-09-01, 2027-08-31, 1)."""
    d = d or date.today()
    y = d.year if d.month >= START_MONTH else d.year - 1
    start = date(y, START_MONTH, 1)
    end = date(y + 1, START_MONTH, 1).replace(day=1)
    end = date.fromordinal(end.toordinal() - 1)
    months = (d.year - start.year) * 12 + d.month - START_MONTH
    return f"{y}-{y + 1}", start, end, months // 3 + 1

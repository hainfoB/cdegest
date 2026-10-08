"""Année professionnelle (septembre → août, mois de début paramétrable) découpée en 2 semestres.

S1 : septembre → février · S2 : mars → août.
"""
from datetime import date

START_MONTH = 9


def _add_months(y, m, k):
    m0 = m - 1 + k
    return y + m0 // 12, m0 % 12 + 1


def _last_day_before(y, m):
    return date.fromordinal(date(y, m, 1).toordinal() - 1)


def training_year(d=None):
    """(label, start, end, semester) — ex. ('2026-2027', 2026-09-01, 2027-08-31, 1)."""
    d = d or date.today()
    y = d.year if d.month >= START_MONTH else d.year - 1
    start = date(y, START_MONTH, 1)
    end = _last_day_before(*_add_months(y, START_MONTH, 12))
    months = (d.year - y) * 12 + d.month - START_MONTH
    return f"{y}-{y + 1}", start, end, 1 if months < 6 else 2


def semester_bounds(label, semester):
    """Dates of S1 / S2 for a training year label '2026-2027'."""
    y = int(label[:4])
    s_y, s_m = _add_months(y, START_MONTH, 0 if semester == 1 else 6)
    e = _last_day_before(*_add_months(s_y, s_m, 6))
    return date(s_y, s_m, 1), e

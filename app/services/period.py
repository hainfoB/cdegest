"""Année professionnelle (septembre → août) découpée en 2 semestres.

S1 : septembre → février · S2 : mars → août. Période « A » = année entière.
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
    """Dates of S1 / S2 (or the whole year when semester is 0) for a label '2026-2027'."""
    y = int(label[:4])
    if not semester:
        return date(y, START_MONTH, 1), _last_day_before(*_add_months(y, START_MONTH, 12))
    s_y, s_m = _add_months(y, START_MONTH, 0 if semester == 1 else 6)
    return date(s_y, s_m, 1), _last_day_before(*_add_months(s_y, s_m, 6))


def year_of(d):
    return training_year(d)[0]


def semester_of(d):
    return training_year(d)[3]


def recent_years(n=3, d=None):
    y = int(training_year(d)[0][:4])
    return [f"{y - k}-{y - k + 1}" for k in range(n)]


class Period:
    """Period selected in the UI: ?y=2026-2027&p=S1|S2|A."""

    def __init__(self, year=None, code=None):
        cur, _s, _e, sem = training_year()
        self.year = year if year and len(year) == 9 and year[4] == "-" else cur
        self.code = code if code in ("S1", "S2", "A") else f"S{sem}"
        self.semester = {"S1": 1, "S2": 2, "A": 0}[self.code]
        self.start, self.end = semester_bounds(self.year, self.semester)

    @classmethod
    def from_request(cls, args):
        return cls(args.get("y"), args.get("p"))

    @property
    def finished(self):
        return date.today() > self.end

    @property
    def started(self):
        return date.today() >= self.start

    @property
    def elapsed(self):
        """Share of the period already elapsed (0..1)."""
        today = date.today()
        if today >= self.end:
            return 1.0
        if today < self.start:
            return 0.0
        return ((today - self.start).days + 1) / ((self.end - self.start).days + 1)

    def args(self):
        return {"y": self.year, "p": self.code}

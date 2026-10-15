"""Calcul des 15 indicateurs communs, par institut, agrégeables par wilaya et au niveau national.

Chaque institut produit des compteurs additifs (« raw ») ; les taux sont calculés à la fin,
ce qui garantit qu'un taux national n'est jamais une moyenne de taux.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import (Attendance, Enrollment, Group, Institute, Objective, Participant, Session, Slot,
                      SurveyResponse)

KPI_FAMILIES = [
    ("activity", ["groups", "sessions", "trained", "teachers", "hours", "fill"]),
    ("attendance", ["attendance", "dropouts", "dropout_rate", "certificates"]),
    ("conversion", ["accepted", "conversion", "completed"]),
    ("quality", ["satisfaction", "response"]),
]
KPIS = [k for _f, ks in KPI_FAMILIES for k in ks]
RATES = {"fill", "attendance", "dropout_rate", "conversion", "satisfaction", "response"}
LOWER_IS_BETTER = {"dropout_rate", "dropouts"}
KPI_ICONS = {
    "groups": "users", "sessions": "layers", "trained": "user-check", "teachers": "briefcase", "hours": "clock",
    "fill": "pie", "attendance": "check", "dropouts": "user-x", "dropout_rate": "trend-down", "certificates": "award",
    "accepted": "thumb", "conversion": "repeat", "completed": "flag", "satisfaction": "smile", "response": "message",
}


def _minutes(s, e):
    h1, m1 = map(int, s.split(":"))
    h2, m2 = map(int, e.split(":"))
    return max(0, (h2 * 60 + m2) - (h1 * 60 + m1))


def _empty():
    return dict(groups=0, sessions=0, participants=set(), teachers=set(), minutes=0, present=0, total=0,
                seats=0, confirmed=0, dropouts=0, started=set(), certs=0, responses=0, satisfied=0,
                eligible=0, accepted=set(), completed=set())


def raw_by_institute(inst_ids, start, end):
    """dict institute_id -> raw counters for the period [start, end]."""
    R = defaultdict(_empty)
    if not inst_ids:
        return R
    today = date.today()
    b = min(end, today)
    ids = list(inst_ids)

    # groups finished in the period (last slot of the group)
    q = (db.session.query(Session.institute_id, Group.id, func.max(Slot.day))
         .join(Group, Group.session_id == Session.id).join(Slot, Slot.group_id == Group.id)
         .filter(Session.institute_id.in_(ids)).group_by(Session.institute_id, Group.id))
    for iid, _gid, last in q:
        if last and start <= last <= b:
            R[iid]["groups"] += 1

    for iid, n in (db.session.query(Session.institute_id, func.count(Session.id))
                   .filter(Session.institute_id.in_(ids), Session.status == "closed",
                           Session.closed_at.between(start, end))
                   .group_by(Session.institute_id)):
        R[iid]["sessions"] += n

    # attendance rows of the period
    q = (db.session.query(Session.institute_id, Attendance.status, Attendance.arrived, Attendance.left,
                          Slot.start, Slot.end, Slot.teacher_id, Enrollment.participant_id, Enrollment.id)
         .select_from(Attendance)
         .join(Slot, Attendance.slot_id == Slot.id)
         .join(Group, Slot.group_id == Group.id)
         .join(Session, Group.session_id == Session.id)
         .join(Enrollment, Attendance.enrollment_id == Enrollment.id)
         .filter(Session.institute_id.in_(ids), Slot.day.between(start, b)))
    for iid, st, arr, lef, s, e, tid, pid, eid in q:
        r = R[iid]
        r["total"] += 1
        r["teachers"].add(tid)
        if st in ("present", "late"):
            r["present"] += 1
            r["participants"].add(pid)
            r["started"].add(eid)
            r["minutes"] += _minutes(arr or s, lef or e)

    # fill rate: sessions starting in the period
    for s in Session.query.filter(Session.institute_id.in_(ids), Session.starts_on.between(start, end),
                                  Session.status != "draft"):
        R[s.institute_id]["seats"] += (s.seats_per_group or 0) * max(len(s.groups), 1)
        R[s.institute_id]["confirmed"] += sum(1 for e in s.enrollments if e.status == "confirmed")

    for iid, n in (db.session.query(Session.institute_id, func.count(Enrollment.id))
                   .join(Enrollment, Enrollment.session_id == Session.id)
                   .filter(Session.institute_id.in_(ids), Enrollment.dropout.is_(True),
                           Enrollment.dropout_on.between(start, end))
                   .group_by(Session.institute_id)):
        R[iid]["dropouts"] += n

    for iid, n in (db.session.query(Session.institute_id, func.count(Enrollment.id))
                   .join(Enrollment, Enrollment.session_id == Session.id)
                   .filter(Session.institute_id.in_(ids), Enrollment.cert_issued_on.between(start, end))
                   .group_by(Session.institute_id)):
        R[iid]["certs"] += n

    # NESDA outcome of the participants trained in the period
    all_pids = set().union(*[r["participants"] for r in R.values()]) if R else set()
    if all_pids:
        status = dict(db.session.query(Participant.id, Participant.nesda_status)
                      .filter(Participant.id.in_(all_pids)))
        for r in R.values():
            r["accepted"] = {p for p in r["participants"] if status.get(p) in ("accepte", "abouti")}
            r["completed"] = {p for p in r["participants"] if status.get(p) == "abouti"}

    # satisfaction
    t0, t1 = datetime.combine(start, datetime.min.time()), datetime.combine(end + timedelta(days=1), datetime.min.time())
    for iid, overall in (db.session.query(Session.institute_id, SurveyResponse.overall)
                         .join(SurveyResponse, SurveyResponse.session_id == Session.id)
                         .filter(Session.institute_id.in_(ids), SurveyResponse.created_at >= t0,
                                 SurveyResponse.created_at < t1)):
        R[iid]["responses"] += 1
        if (overall or 0) >= 4:
            R[iid]["satisfied"] += 1
    for iid, n in (db.session.query(Session.institute_id, func.count(Enrollment.id))
                   .join(Enrollment, Enrollment.session_id == Session.id)
                   .filter(Session.institute_id.in_(ids), Session.status == "closed",
                           Session.closed_at.between(start, end), Enrollment.status == "confirmed",
                           Enrollment.dropout.is_(False))
                   .group_by(Session.institute_id)):
        R[iid]["eligible"] += n
    return R


def merge(raws):
    out = _empty()
    for r in raws:
        for k, v in r.items():
            if isinstance(v, set):
                out[k] = out[k] | v
            else:
                out[k] += v
    return out


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def finalize(r):
    trained = len(r["participants"])
    return {
        "groups": r["groups"],
        "sessions": r["sessions"],
        "trained": trained,
        "teachers": len(r["teachers"]),
        "hours": round(r["minutes"] / 60),
        "fill": _pct(r["confirmed"], r["seats"]),
        "attendance": _pct(r["present"], r["total"]),
        "dropouts": r["dropouts"],
        "dropout_rate": _pct(r["dropouts"], len(r["started"])),
        "certificates": r["certs"],
        "accepted": len(r["accepted"]),
        "conversion": _pct(len(r["accepted"]), trained),
        "completed": len(r["completed"]),
        "satisfaction": _pct(r["satisfied"], r["responses"]),
        "response": _pct(r["responses"], r["eligible"]),
    }


def kpis_for_institutes(inst_ids, period):
    raw = raw_by_institute(inst_ids, period.start, period.end)
    return finalize(merge(raw.values()))


# ------------------------------------------------------------------ objectives

def targets(period, wilaya_id, institute_id=None):
    q = Objective.query.filter_by(year=period.year, semester=period.semester, wilaya_id=wilaya_id,
                                  institute_id=institute_id)
    return {o.kpi: o.target for o in q}


def kpi_status(kpi, value, target, period):
    """met | track | late | missed | none."""
    if target is None:
        return "none"
    if value is None:
        return "missed" if period.finished else ("late" if period.started else "track")
    lower = kpi in LOWER_IS_BETTER
    reached = value <= target if lower else value >= target
    if period.finished:
        return "met" if reached else "missed"
    if lower and kpi not in RATES:
        # a count where less is better: on track while below the prorated ceiling
        return "track" if value <= target * period.elapsed else "late"
    if reached and kpi not in RATES:
        return "met"
    if kpi in RATES:
        return "track" if reached else "late"
    return "track" if value >= target * period.elapsed else "late"


def overall_status(statuses, period):
    s = [x for x in statuses if x != "none"]
    if not s:
        return "none"
    met = sum(1 for x in s if x == "met")
    ok = sum(1 for x in s if x in ("met", "track"))
    if period.finished:
        return "met" if met / len(s) >= 0.8 else "missed"
    if met == len(s):
        return "met"
    return "track" if ok / len(s) >= 0.8 else "late"


def evaluate(values, tg, period):
    """Per-KPI status + overall status."""
    per = {k: kpi_status(k, values.get(k), tg.get(k), period) for k in KPIS}
    return per, overall_status(per.values(), period)


def wilaya_table(wilayas, period):
    """For the national view: one line per wilaya with KPIs, targets and status (2 queries per wilaya max)."""
    insts = Institute.query.filter(Institute.wilaya_id.in_([w.id for w in wilayas])).all()
    by_w = defaultdict(list)
    for i in insts:
        by_w[i.wilaya_id].append(i.id)
    raw = raw_by_institute([i.id for i in insts], period.start, period.end)
    all_obj = Objective.query.filter_by(year=period.year, semester=period.semester, institute_id=None).all()
    obj_by_w = defaultdict(dict)
    for o in all_obj:
        obj_by_w[o.wilaya_id][o.kpi] = o.target
    rows = []
    for w in wilayas:
        vals = finalize(merge(raw[i] for i in by_w[w.id] if i in raw))
        per, st = evaluate(vals, obj_by_w[w.id], period)
        rows.append({"wilaya": w, "n_inst": len(by_w[w.id]), "values": vals, "targets": obj_by_w[w.id],
                     "per": per, "status": st})
    return rows


def institute_table(institutes, period):
    raw = raw_by_institute([i.id for i in institutes], period.start, period.end)
    rows = []
    for i in institutes:
        vals = finalize(raw[i.id]) if i.id in raw else finalize(_empty())
        tg = targets(period, i.wilaya_id, i.id)
        per, st = evaluate(vals, tg, period)
        rows.append({"institute": i, "values": vals, "targets": tg, "per": per, "status": st})
    return rows


def fmt(kpi, v):
    if v is None:
        return "—"
    if kpi in RATES:
        return f"{v:.0f} %" if v == int(v) else f"{v:.1f} %"
    return f"{int(v):,}".replace(",", " ")

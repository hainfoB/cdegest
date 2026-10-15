"""Règles métier : assiduité, abandons, clôture, validation NESDA, attestations."""
from collections import defaultdict
from datetime import date

from flask import current_app

from ..extensions import db
from ..models import AuditLog, Attendance, Enrollment
from ..utils import utcnow


def past_slots(group, today=None):
    today = today or date.today()
    return [s for s in group.slots if s.day <= today] if group else []


def enrollment_stats(enr, today=None):
    """dict: expected, present, absent, rate (%), minutes."""
    slots = past_slots(enr.group, today)
    ids = {s.id for s in slots}
    att = {a.slot_id: a for a in enr.attendances if a.slot_id in ids}
    present = sum(1 for a in att.values() if a.status in ("present", "late"))
    minutes = sum(a.minutes for a in att.values())
    expected = len(slots)
    return {
        "expected": expected,
        "present": present,
        "absent": expected - present,
        "rate": round(100.0 * present / expected) if expected else None,
        "minutes": minutes,
        "marks": att,
    }


def eligible(enr, stats=None):
    s = enr.session
    if enr.status != "confirmed" or enr.dropout or not enr.group:
        return False
    stats = stats or enrollment_stats(enr)
    finished = enr.group.last_day is not None and enr.group.last_day <= date.today()
    return finished and stats["rate"] is not None and stats["rate"] >= (s.min_attendance or 0)


def detect_dropouts(session, today=None, user=None):
    """Absent (no presence) on the last 2 past training days after having started → abandon."""
    today = today or date.today()
    n = 0
    for enr in session.enrollments:
        if enr.status != "confirmed" or enr.dropout or not enr.group:
            continue
        slots = past_slots(enr.group, today)
        days = sorted({s.day for s in slots})
        if len(days) < 3:
            continue
        marks = {a.slot_id: a.status for a in enr.attendances}
        by_day = defaultdict(list)
        for s in slots:
            by_day[s.day].append(marks.get(s.id))
        present_days = [d for d in days if any(m in ("present", "late") for m in by_day[d])]
        last2 = days[-2:]
        if present_days and all(not any(m in ("present", "late") for m in by_day[d]) for d in last2) \
                and all(any(m is not None for m in by_day[d]) for d in last2):
            enr.dropout, enr.dropout_on, enr.dropout_reason = True, last2[-1], "absences"
            n += 1
    if n:
        AuditLog.log("dropouts.auto", target=f"session:{session.id}", details=f"{n} abandon(s)", user=user)
    return n


def close_session(session, user=None, today=None):
    today = today or date.today()
    detect_dropouts(session, today, user)
    for enr in session.enrollments:
        if enr.status != "confirmed" or enr.dropout or not enr.group:
            continue
        st = enrollment_stats(enr, today)
        if st["present"] and st["rate"] is not None and st["rate"] < (session.min_attendance or 0):
            enr.dropout, enr.dropout_on, enr.dropout_reason = True, today, "seuil"
    session.status = "closed"
    session.closed_at = today
    AuditLog.log("session.close", target=f"session:{session.id}", user=user)


def dg_validation_required():
    return current_app.config.get("NESDA_DG_VALIDATION", False)


def nesda_submit(session, user):
    if session.status != "closed" or session.nesda_status not in ("none", "rejected"):
        return False
    session.nesda_status = "submitted"
    session.nesda_submitted_at = utcnow()
    session.nesda_note = None
    AuditLog.log("nesda.submit", target=f"session:{session.id}", user=user)
    return True


def nesda_validate(session, user, today=None):
    """Wilaya NESDA representative (or DG) validates the attendance lists."""
    from ..security import NESDA_DG
    if user.role == NESDA_DG:
        if session.nesda_status not in ("submitted", "wilaya_ok"):
            return False
        session.nesda_dg_by_id, session.nesda_dg_at = user.id, utcnow()
        session.nesda_status = "validated"
    else:
        if session.nesda_status != "submitted":
            return False
        session.nesda_w_by_id, session.nesda_w_at = user.id, utcnow()
        session.nesda_status = "wilaya_ok" if dg_validation_required() else "validated"
    AuditLog.log("nesda.validate", target=f"session:{session.id}", details=session.nesda_status, user=user)
    if session.nesda_status == "validated":
        issue_certificates(session, today)
    return True


def nesda_reject(session, user, note):
    if session.nesda_status not in ("submitted", "wilaya_ok"):
        return False
    session.nesda_status = "rejected"
    session.nesda_note = (note or "").strip()[:1000]
    AuditLog.log("nesda.reject", target=f"session:{session.id}", details=session.nesda_note, user=user)
    return True


def issue_certificates(session, today=None):
    today = today or date.today()
    n = 0
    wcode = session.institute.wilaya.code
    for enr in session.enrollments:
        if enr.cert_no or not eligible(enr):
            continue
        enr.cert_no = f"CDE{wcode}-{today.year}-{enr.id:06d}"
        enr.cert_issued_on = today
        n += 1
    return n


def mark(slot, enr, status, user, method="appel", arrived=None, left=None, correction=False):
    a = Attendance.query.filter_by(slot_id=slot.id, enrollment_id=enr.id).first()
    if a is None:
        a = Attendance(slot_id=slot.id, enrollment_id=enr.id, status=status)
        db.session.add(a)
    a.status = status
    a.arrived = arrived or None
    a.left = left or None
    a.method = "correction" if correction else method
    a.corrected = a.corrected or correction
    a.marked_by_id = getattr(user, "id", None)
    a.marked_at = utcnow()
    return a


def place_enrollment(enr):
    """Assign a group with free seats; otherwise waiting list."""
    s = enr.session
    for g in s.groups:
        taken = Enrollment.query.filter_by(group_id=g.id, status="confirmed").count()
        if taken < (s.seats_per_group or 0):
            enr.group = g
            enr.status = "confirmed" if s.auto_confirm else "pending"
            return
    enr.status = "waitlist"

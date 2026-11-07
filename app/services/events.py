"""Événements métier → messages du catalogue (EP-11). Chaque fonction est appelée au moment où l'événement a lieu."""
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import Candidature, Group, Institute, Notification, Session, Slot, User
from ..utils import utcnow
from .messages import CHANGE
from .notify import link, local_now, recipient, send

ROLE_NAMES = {
    "fr": {"admin": "administrateur", "mfep": "MFEP", "dfep": "DFEP", "coord": "coordinateur CDE", "resp": "responsable CDE",
           "formateur": "enseignant", "nesda": "représentant NESDA", "nesda_dg": "DG NESDA", "candidat": "candidat",
           "stagiaire": "stagiaire"},
    "ar": {"admin": "مسؤول المنصة", "mfep": "الوزارة", "dfep": "مديرية التكوين", "coord": "منسق المراكز", "resp": "مسؤول المركز",
           "formateur": "أستاذ", "nesda": "ممثل NESDA", "nesda_dg": "المديرية العامة NESDA", "candidat": "مترشح",
           "stagiaire": "متربص"},
}


def _d(d):
    return d.strftime("%d/%m/%Y") if d else ""


def _first_hour(s):
    days = [sl for g in s.groups for sl in g.slots]
    return min(days, key=lambda x: (x.day, x.start)).start.replace(":", " h ") if days else ""


# ------------------------------------------------------------------ A — sécurité

def code_sent(user, otp, code):
    r = recipient(user)
    return send("M-01", r, {"code": code}, f"otp:{otp.id}", channel=otp.channel)


def security_alert(user, what_key):
    what = {"new_device": {"fr": "connexion depuis un nouvel appareil", "ar": "دخول من جهاز جديد"},
            "password": {"fr": "mot de passe modifié", "ar": "تغيير كلمة المرور"},
            "channel": {"fr": "coordonnées de contact modifiées", "ar": "تغيير معلومات الاتصال"}}[what_key]
    r = recipient(user)
    return send("M-02", r, {"what": what.get(r["lang"], what["fr"]), "date": local_now().strftime("%d/%m/%Y %H:%M")},
                f"sec:{user.id}:{what_key}:{utcnow().timestamp():.0f}")


def habilitation_changed(hab, change, by):
    u = hab.user
    r = recipient(u)
    lg = r["lang"]
    lk = link("auth.activate", token=u.invite_token) if change == "invited" and u.invite_token else link("auth.login")
    return send("M-03", r, {"role": ROLE_NAMES[lg].get(hab.role, hab.role), "scope": hab.scope_name(lg),
                            "change": CHANGE[change][lg], "by": by.name if by else "CDEgest", "link": lk},
                f"hab:{hab.id}:{change}:{utcnow().timestamp():.0f}")


# ------------------------------------------------------------------ B — dossier

def candidature_received(c):
    r = recipient(candidature=c)
    return send("M-04", r, {"ref": c.short_ref, "date": _d(c.created_at.date() if c.created_at else date.today()),
                            "cde": c.institute.name(r["lang"]) if c.institute else "", "link": link("espace.home")},
                f"cand:{c.id}:received")


def candidature_oriented(c, s):
    r = recipient(candidature=c)
    return send("M-06", r, {"ref": c.short_ref, "session": s.title, "start": _d(s.starts_on), "link": link("espace.home")},
                f"cand:{c.id}:oriented:{s.id}")


def candidature_rejected(c):
    r = recipient(candidature=c)
    return send("M-07", r, {"ref": c.short_ref, "link": link("espace.home")}, f"cand:{c.id}:rejected")


def enrollment_confirmed(e):
    """Convocation (M-08) et habilitation « stagiaire » sur le CDE de la session."""
    p, s = e.participant, e.session
    if p.user is not None:
        p.user.grant("stagiaire", institute=s.institute, reason=f"session:{s.id}")
    r = recipient(participant=p)
    return send("M-08", r, {"session": s.title, "start": _d(s.starts_on), "hour": _first_hour(s) or "8 h 30",
                            "cde": s.institute.name(r["lang"]), "link": link("public.ticket", token=e.token)},
                f"enr:{e.id}:confirmed")


def planning_changed(group, what):
    """Regroupé : un message par groupe et par heure au plus (M-10)."""
    hour = local_now().strftime("%Y%m%d%H")
    out = []
    for e in group.enrollments:
        if e.status != "confirmed":
            continue
        r = recipient(participant=e.participant)
        out += send("M-10", r, {"session": group.session.title, "what": what, "link": link("public.ticket", token=e.token)},
                    f"plan:{group.id}:{e.id}:{hour}")
    return out


def attestation_ready(e):
    r = recipient(participant=e.participant)
    return send("M-12", r, {"cde": e.session.institute.name(r["lang"]), "link": link("public.verify", cert_no=e.cert_no)},
                f"cert:{e.id}")


# ------------------------------------------------------------------ D — agents (immédiat quand cela bloque un autre acteur)

def session_submitted(s):
    out = []
    reps = User.having("nesda", wilaya_id=s.institute.wilaya_id).all()
    for u in reps:
        out += send("M-16", recipient(u), {"session": s.title, "cde": s.institute.name(u.lang if u.lang in ("ar", "fr") else "fr"),
                                           "n": len(s.confirmed), "link": link("nesda.review", sid=s.id)},
                    f"sub:{s.id}:{u.id}:{(s.nesda_submitted_at or utcnow()).timestamp():.0f}")
    return out


def session_rejected(s):
    out = []
    for u in User.having("resp", institute_id=s.institute_id).all():
        out += send("M-17", recipient(u), {"session": s.title, "note": s.nesda_note or "", "link": link("sessions.view", sid=s.id)},
                    f"rej:{s.id}:{u.id}:{utcnow().timestamp():.0f}")
    return out


def report_status(report, what_key, recipients):
    what = {"generated": {"fr": "généré", "ar": "أُعدّ"}, "transmitted": {"fr": "validé et transmis", "ar": "صودق عليه وأُرسل"}}[what_key]
    out = []
    for u in recipients:
        r = recipient(u)
        label = f"{report.year} S{report.semester} — " + (report.institute.name(r["lang"]) if report.institute else report.wilaya.name(r["lang"]))
        out += send("M-18", r, {"report": label, "what": what.get(r["lang"], what["fr"]), "link": link("reports.view", rid=report.id)},
                    f"rep:{report.id}:{what_key}:{u.id}")
    return out


# ------------------------------------------------------------------ rappels (C) et résumés (D) — `flask notify-reminders`

def run_reminders(today=None):
    today = today or local_now().date()
    n = 0
    # M-05 : demande toujours à l'étude 30 jours après le dépôt
    limit = datetime.combine(today - timedelta(days=30), datetime.min.time())
    for c in Candidature.query.filter(Candidature.status.in_(("nouvelle", "retenue")), Candidature.created_at <= limit):
        n += len(send("M-05", recipient(candidature=c), {"ref": c.short_ref, "cde": c.institute.name("fr") if c.institute else "",
                                                         "link": link("espace.home")}, f"cand:{c.id}:j30"))
    # M-09 : rappel deux jours avant le premier jour
    for s in Session.query.filter(Session.starts_on == today + timedelta(days=2), Session.status.in_(("open", "running"))):
        for e in s.confirmed:
            n += len(send("M-09", recipient(participant=e.participant), {"start": _d(s.starts_on), "hour": _first_hour(s) or "8 h 30",
                                                                         "link": link("public.ticket", token=e.token)}, f"enr:{e.id}:j2"))
    # M-11 : questionnaire à la clôture, une relance à J+3
    for s in Session.query.filter(Session.status == "closed", Session.closed_at >= today - timedelta(days=3)):
        tag = "j3" if s.closed_at == today - timedelta(days=3) else "close"
        for e in s.confirmed:
            if not e.survey_done and not e.dropout:
                n += len(send("M-11", recipient(participant=e.participant), {"session": s.title,
                                                                             "link": link("public.survey", token=e.token)},
                              f"enr:{e.id}:survey:{tag}"))
    # M-13 : compte de candidat inactif (2 ans) — avertissement 30 jours avant suppression (RG-45)
    edge = utcnow() - timedelta(days=730 - 30)
    for u in User.query.filter(User.last_login_at.isnot(None), User.last_login_at <= edge):
        if all(h.role == "candidat" for h in u.habilitations):
            n += len(send("M-13", recipient(u), {"date": _d((u.last_login_at + timedelta(days=730)).date()),
                                                  "link": link("auth.login")}, f"inactive:{u.id}:{u.last_login_at:%Y%m%d}"))
    # M-15 : appel non fait, à partir de 18 h le jour du créneau
    if local_now().hour >= 18 or today != local_now().date():
        for sl in Slot.query.filter(Slot.day == today, Slot.called_at.is_(None), Slot.cancelled.is_(False)):
            if sl.teacher is not None:
                n += len(send("M-15", recipient(sl.teacher), {"slot": f"{sl.start}–{sl.end}", "session": sl.group.session.title,
                                                              "link": link("sessions.roll_call", slot_id=sl.id)}, f"slot:{sl.id}:nocall"))
    return n


def run_digests(today=None):
    """M-14 : résumé quotidien du responsable CDE (rien n'est envoyé s'il n'y a rien à signaler) ; M-16 en résumé pour la NESDA."""
    from ..models import Habilitation
    today = today or local_now().date()
    n = 0
    for h in Habilitation.query.filter_by(role="resp", status="active"):
        if not h.is_valid() or h.institute is None:
            continue
        iid = h.institute_id
        since = datetime.combine(today - timedelta(days=1), datetime.min.time())
        new = Candidature.query.filter(Candidature.institute_id == iid, Candidature.created_at >= since).count()
        old = Candidature.query.filter(Candidature.institute_id == iid, Candidature.status.in_(("nouvelle", "retenue")),
                                       Candidature.created_at <= datetime.combine(today - timedelta(days=15), datetime.min.time())).count()
        unver = Candidature.query.filter(Candidature.institute_id == iid, Candidature.status.in_(("nouvelle", "retenue")),
                                         Candidature.identity_source != "etat_civil").count()
        nocall = (Slot.query.join(Group, Slot.group_id == Group.id).join(Session, Group.session_id == Session.id)
                  .filter(Session.institute_id == iid, Slot.day < today, Slot.day >= today - timedelta(days=7),
                          Slot.called_at.is_(None), Slot.cancelled.is_(False)).count())
        rejected = Session.query.filter_by(institute_id=iid, nesda_status="rejected").count()
        fails = (Notification.query.join(Candidature, Candidature.user_id == Notification.user_id)
                 .filter(Candidature.institute_id == iid, Notification.status == "failed",
                         Notification.created_at >= since).with_entities(Notification.user_id).distinct().count())
        lg = h.user.lang if h.user.lang in ("ar", "fr") else "fr"
        L = {"fr": ["{} nouvelle(s) demande(s)", "{} demande(s) de plus de 15 jours", "{} dossier(s) non vérifié(s)",
                    "{} appel(s) manquant(s) (7 jours)", "{} session(s) renvoyée(s) par la NESDA", "{} candidat(s) injoignable(s)"],
             "ar": ["{} طلب(ات) جديدة", "{} طلب(ات) تجاوزت 15 يوماً", "{} ملف(ات) غير مُتحقّق منها",
                    "{} مناداة غير منجزة (7 أيام)", "{} دورة(ات) أعادتها NESDA", "{} مترشح(ون) تعذّر الوصول إليهم"]}[lg]
        vals = [new, old, unver, nocall, rejected, fails]
        lines = "\n".join("• " + L[k].format(v) for k, v in enumerate(vals) if v)
        if not lines:
            continue
        n += len(send("M-14", recipient(h.user), {"date": _d(today), "cde": h.institute.name(lg), "lines": lines,
                                                  "link": link("main.dashboard")}, f"digest:{h.id}:{today:%Y%m%d}"))
    for h in Habilitation.query.filter_by(role="nesda", status="active"):
        pend = (Session.query.join(Institute, Session.institute_id == Institute.id)
                .filter(Session.nesda_status == "submitted", Institute.wilaya_id == h.wilaya_id).all())
        if not pend:
            continue
        lg = h.user.lang if h.user.lang in ("ar", "fr") else "fr"
        n += len(send("M-16", recipient(h.user), {"session": ", ".join(s.title for s in pend[:3]) + (" …" if len(pend) > 3 else ""),
                                                  "cde": f"{len(pend)} session(s)", "n": sum(len(s.confirmed) for s in pend),
                                                  "link": link("nesda.queue")}, f"digest-nesda:{h.id}:{today:%Y%m%d}"))
    return n

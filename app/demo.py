"""Données de démonstration FICTIVES : catalogue, wilayas, CDE, sessions sur deux années professionnelles,
présences, abandons, validations NESDA, attestations, satisfaction, objectifs, programmes et rapports.

Déterministe (graine fixe) et relatif à la date du jour, pour que l'appel « du jour » existe toujours.
"""
import json
import math
import random
import secrets
from datetime import date, datetime, time, timedelta

from .extensions import db
from .models import (Attendance, Enrollment, Group, Institute, Module, Objective, Participant, Programme,
                     ProgrammeLine, Report, Session, Slot, SurveyQuestion, SurveyResponse, User, Wilaya,
                     WorkshopTemplate)
from .services import kpi as K
from .services import training as T
from .services.period import Period, semester_bounds, training_year

R = random.Random(2026)

CATALOGUE = [
    # code, theme, kind, fr, ar, hours, modules (fr)
    ("ENT-01", "Idée", "atelier", "Idée et opportunité d'affaires", "الفكرة وفرصة الأعمال", 9,
     ["Générer des idées", "Analyser les opportunités", "Valider le besoin client"]),
    ("ENT-02", "Marché", "atelier", "Étude de marché", "دراسة السوق", 9,
     ["Connaître son marché", "Enquête de terrain", "Analyse de la concurrence"]),
    ("ENT-03", "Modèle", "atelier", "Business Model Canvas", "نموذج العمل التجاري", 9,
     ["Proposition de valeur", "Clients et canaux", "Revenus et coûts"]),
    ("ENT-04", "Gestion", "atelier", "Plan d'affaires", "مخطط الأعمال", 12,
     ["Plan financier", "Prévisions sur trois ans", "Rédaction du dossier", "Soutenance blanche"]),
    ("ENT-05", "Juridique", "atelier", "Démarches juridiques et administratives", "الإجراءات القانونية والإدارية", 9,
     ["Formes juridiques", "Registre et fiscalité", "Statut d'auto-entrepreneur"]),
    ("ENT-06", "Gestion", "atelier", "Gestion financière de la micro-entreprise", "التسيير المالي للمؤسسة المصغرة", 9,
     ["Trésorerie", "Coûts et prix de vente", "Tableau de bord"]),
    ("ENT-07", "Numérique", "atelier", "Marketing digital", "التسويق الرقمي", 9,
     ["Réseaux sociaux", "Création de contenu", "Vente en ligne"]),
    ("ENT-08", "Communication", "seminaire", "Pitch et présentation du projet", "تقديم المشروع والإقناع", 6,
     ["Structurer son pitch", "Simulation devant un jury"]),
    ("ENT-09", "Bootcamp", "bootcamp", "Bootcamp « De l'idée au projet »", "معسكر «من الفكرة إلى المشروع»", 12,
     ["Idéation", "Prototype", "Modèle économique", "Pitch final"]),
    ("ENT-10", "Dispositifs", "seminaire", "Dispositifs d'appui à la création d'entreprise", "أجهزة دعم إنشاء المؤسسات", 6,
     ["Panorama des dispositifs (NESDA, CNAC, ANGEM)", "Constituer son dossier NESDA"]),
]

SURVEY = [
    ("Le contenu répondait à mes attentes", "المحتوى استجاب لتوقعاتي", "The content met my expectations"),
    ("Les enseignants étaient clairs et disponibles", "الأساتذة كانوا واضحين ومتاحين", "Teachers were clear and available"),
    ("L'organisation (horaires, salle, matériel) était bonne", "التنظيم (التوقيت، القاعة، الوسائل) كان جيدًا",
     "The organisation (times, room, equipment) was good"),
    ("Je saurai utiliser ce que j'ai appris pour mon projet", "سأستطيع استعمال ما تعلمته في مشروعي",
     "I will be able to use what I learned for my project"),
    ("La durée de la formation était adaptée", "مدة التكوين كانت مناسبة", "The length of the training was appropriate"),
    ("Globalement, je suis satisfait(e) de la formation", "إجمالًا، أنا راضٍ عن التكوين", "Overall, I am satisfied with the training"),
]

# wilayas with fictitious activity: code -> list of (institute code, fr, ar)
DEMO_INST = {
    "19": [("INSFP-STF-01", "INSFP Sétif 01", "المعهد الوطني المتخصص في التكوين المهني سطيف 01"),
           ("INSFP-STF-02", "INSFP Sétif 02", "المعهد الوطني المتخصص في التكوين المهني سطيف 02")],
    "28": [("INSFP-MSL-01", "INSFP M'Sila 01", "المعهد الوطني المتخصص في التكوين المهني المسيلة 01")],
    "16": [("INSFP-ALG-01", "INSFP Alger — Bab Ezzouar", "المعهد الوطني المتخصص في التكوين المهني باب الزوار"),
           ("INSFP-ALG-02", "INSFP Alger — Birkhadem", "المعهد الوطني المتخصص في التكوين المهني بئر خادم")],
    "31": [("INSFP-ORN-01", "INSFP Oran 01", "المعهد الوطني المتخصص في التكوين المهني وهران 01"),
           ("INSFP-ORN-02", "INSFP Oran 02", "المعهد الوطني المتخصص في التكوين المهني وهران 02")],
    "25": [("INSFP-CST-01", "INSFP Constantine 01", "المعهد الوطني المتخصص في التكوين المهني قسنطينة 01")],
    "05": [("INSFP-BTN-01", "INSFP Batna 01", "المعهد الوطني المتخصص في التكوين المهني باتنة 01")],
    "06": [("INSFP-BJA-01", "INSFP Béjaïa 01", "المعهد الوطني المتخصص في التكوين المهني بجاية 01")],
    "13": [("INSFP-TLM-01", "INSFP Tlemcen 01", "المعهد الوطني المتخصص في التكوين المهني تلمسان 01")],
    "30": [("INSFP-OGX-01", "INSFP Ouargla 01", "المعهد الوطني المتخصص في التكوين المهني ورقلة 01")],
    "68": [("INSFP-BSD-01", "INSFP Bou Saâda 01", "المعهد الوطني المتخصص في التكوين المهني بوسعادة 01")],
}
# relative "performance" of each wilaya (drives attendance and volume) — fictitious
PERF = {"34": 1.0, "19": 1.05, "28": 0.45, "16": 1.1, "31": 0.9, "25": 0.85, "05": 0.6, "06": 0.8, "13": 0.75,
        "30": 0.55, "68": 0.65}

M_FIRST = ["Mohamed", "Ahmed", "Yacine", "Amine", "Walid", "Sofiane", "Karim", "Abdelkader", "Bilal", "Hamza",
           "Riad", "Nabil", "Mehdi", "Oussama", "Islam", "Ayoub", "Anis", "Fares", "Zakaria", "Rachid", "Lyes",
           "Samir", "Toufik", "Adel"]
F_FIRST = ["Amina", "Sara", "Imane", "Meriem", "Yasmine", "Khadidja", "Nour El Houda", "Asma", "Lina", "Chaima",
           "Rania", "Hadjer", "Selma", "Ikram", "Nesrine", "Wafa", "Soumia", "Fatima Zohra", "Lamia", "Dounia",
           "Maroua", "Sabrina"]
LAST = ["Benali", "Bouzid", "Hamidi", "Khelifi", "Mansouri", "Belkacem", "Saadi", "Boudiaf", "Meziane", "Rahmani",
        "Cherif", "Haddad", "Ziani", "Benyahia", "Brahimi", "Djebbar", "Ait Ahmed", "Larbi", "Messaoudi",
        "Bensalem", "Kaci", "Taleb", "Zerrouki", "Amrani", "Bouchama", "Guerfi", "Lounis", "Hadj Ali", "Ferhat",
        "Boukhalfa", "Benamara", "Saidi", "Zitouni", "Mekki", "Bouaziz", "Achour"]
SPECIALTIES = ["Informatique", "Comptabilité", "Électricité bâtiment", "Hôtellerie", "Agriculture", "Mécanique auto",
               "Couture", "Pâtisserie", "Plomberie", "Infographie", "Froid et climatisation", "Secrétariat"]
TEACHER_NAMES = ["Mme Bensaid", "M. Kadri", "Mme Ouali", "M. Hamel", "Mme Larbaoui", "M. Rezig", "Mme Taibi",
                 "M. Daoud", "Mme Feddal", "M. Chouaki"]


def _pwd():
    return secrets.token_urlsafe(24)


def _workdays(start, n, force=None):
    """n Algerian working days (Sunday–Thursday) from start; `force` day is always included."""
    days, d = [], start
    while len(days) < n:
        if d.weekday() not in (4, 5) or d == force:
            days.append(d)
        d += timedelta(days=1)
    if force and force not in days:
        days[-1] = force
        days.sort()
    return days


def _phone():
    return "0" + R.choice("567") + "".join(R.choice("0123456789") for _ in range(8))


def _user(email, name, role, inst=None, wilaya=None):
    u = User.query.filter_by(email=email).first()
    if u:
        return u
    u = User(email=email, name=name, role=role, institute=inst, wilaya=wilaya or (inst.wilaya if inst else None),
             lang="ar")
    u.set_password(_pwd())
    db.session.add(u)
    return u


def seed_demo(today=None):
    today = today or date.today()
    if Session.query.first():
        return "seed-demo: données déjà présentes, rien à faire"

    # ---------------- catalogue & survey
    tpls = {}
    for code, theme, kind, fr, ar, hours, mods in CATALOGUE:
        tpl = WorkshopTemplate.query.filter_by(code=code).first() or WorkshopTemplate(code=code)
        tpl.theme, tpl.kind, tpl.title_fr, tpl.title_ar, tpl.hours = theme, kind, fr, ar, hours
        tpl.objectives_fr = " · ".join(mods)
        db.session.add(tpl)
        tpls[code] = (tpl, mods)
    if not SurveyQuestion.query.first():
        for k, (fr, ar, en) in enumerate(SURVEY, 1):
            db.session.add(SurveyQuestion(order=k, text_fr=fr, text_ar=ar, text_en=en, is_overall=k == len(SURVEY)))
    db.session.flush()

    # ---------------- organisation
    wil = {w.code: w for w in Wilaya.query}
    insts_by_w = {"34": Institute.query.join(Wilaya).filter(Wilaya.code == "34").order_by(Institute.code).all()}
    for wcode, lst in DEMO_INST.items():
        insts_by_w[wcode] = []
        for code, fr, ar in lst:
            i = Institute.query.filter_by(code=code).first()
            if not i:
                i = Institute(code=code, wilaya=wil[wcode], name_fr=fr, name_ar=ar, cde_opened_on=date(2025, 10, 1))
                db.session.add(i)
            insts_by_w[wcode].append(i)
        w = wil[wcode]
        w.is_demo = True
        _user(f"dfep.w{wcode}@cdegest.dz", f"DFEP {w.name_fr}", "dfep", wilaya=w)
        _user(f"coord.w{wcode}@cdegest.dz", f"Coordinateur CDE {w.name_fr}", "coord", wilaya=w)
        _user(f"nesda.w{wcode}@cdegest.dz", f"Représentant NESDA {w.name_fr}", "nesda", wilaya=w)
    db.session.flush()

    teachers = {}
    for wcode, insts in insts_by_w.items():
        for i in insts:
            if not User.query.filter_by(institute_id=i.id, role="resp").first():
                _user(f"resp.{i.code.lower()}@cdegest.dz", f"Responsable CDE {i.code}", "resp", inst=i)
            lst = User.query.filter_by(institute_id=i.id, role="formateur").all()
            names = R.sample(TEACHER_NAMES, 4)
            k = 0
            while len(lst) < 4:
                lst.append(_user(f"ens{k + 1}.{i.code.lower()}@cdegest.dz", names[k], "formateur", inst=i))
                k += 1
            teachers[i.id] = lst
    db.session.flush()
    demo_teacher = User.query.filter_by(email="formateur.bba01@cdegest.dz").first()
    if demo_teacher and demo_teacher.name == "Enseignant INSFP BBA 01":
        demo_teacher.name = "Mme Yasmina Belaid"

    # ---------------- sessions
    cur_label, cur_start, cur_end, _sem = training_year(today)
    prev_label = f"{int(cur_label[:4]) - 1}-{int(cur_label[:4])}"
    p_s1, p_s2 = semester_bounds(prev_label, 1), semester_bounds(prev_label, 2)
    people = []

    def make_session(inst, code, start, n_groups, per_group, perf, status, force_today=False, mfirst_teacher=None):
        tpl, mods = tpls[code]
        tch = teachers[inst.id][:]
        if mfirst_teacher and mfirst_teacher in tch:
            tch.remove(mfirst_teacher)
            tch.insert(0, mfirst_teacher)
        s = Session(institute=inst, template=tpl, title=tpl.title_fr, mode=R.choice(["onsite"] * 5 + ["hybrid"]),
                    location=f"{inst.name_fr} — salle CDE", seats_per_group=per_group + R.choice([0, 2, 4]),
                    min_attendance=80, auto_confirm=True, status="draft")
        db.session.add(s)
        modules = []
        for k, title in enumerate(mods):
            modules.append(Module(session=s, order=k + 1, title=title, hours=3, supervisor=tch[k % len(tch)]))
        db.session.add_all(modules)
        plan = [m for m in modules for _ in range(2)]          # 2 slots of 3 h per module
        days = _workdays(start, len(plan), force=today if force_today else None)
        s.starts_on, s.ends_on = days[0], days[-1]
        sup = [m.supervisor for m in modules]
        for gi in range(n_groups):
            g = Group(session=s, name=f"G{gi + 1}", room=f"Salle {R.randint(1, 12)}")
            db.session.add(g)
            for k, (m, d) in enumerate(zip(plan, days)):
                teacher = sup[(k // 2 + gi) % len(sup)]
                db.session.add(Slot(group=g, module=m, teacher=teacher, day=d,
                                    start="09:00" if gi % 2 == 0 else "13:00", end="12:00" if gi % 2 == 0 else "16:00"))
            n_part = per_group - R.randint(0, 3) if status != "open" else R.randint(per_group // 3, per_group - 2)
            for _ in range(n_part):
                sex = R.choice("FFM")
                p = Participant(first_name=R.choice(F_FIRST if sex == "F" else M_FIRST), last_name=R.choice(LAST),
                                sex=sex, phone=_phone(), wilaya_id=inst.wilaya_id, origin_institute_id=inst.id,
                                specialty=R.choice(SPECIALTIES), status=R.choice(["stagiaire", "diplome", "diplome"]),
                                birth_date=date(R.randint(1996, 2006), R.randint(1, 12), R.randint(1, 28)),
                                consent_at=datetime.combine(start - timedelta(days=10), time(10)))
                db.session.add(p)
                e = Enrollment(session=s, group=g, participant=p, status="confirmed",
                               source=R.choice(["public", "public", "cde"]),
                               created_at=datetime.combine(start - timedelta(days=R.randint(5, 20)), time(11)))
                db.session.add(e)
                people.append(p)
        db.session.flush()
        if status == "open":
            s.status = "open"
            return s
        # attendance on past slots
        # teacher absences (cancelled slots) and missing roll calls: frequent where the wilaya struggles
        p_cancel = 0.18 if perf < 0.6 else (0.04 if perf < 0.8 else 0.01)
        p_uncalled = 0.08 if perf < 0.6 else 0.0
        for g in s.groups:
            past = [sl for sl in g.slots if sl.day < today or (sl.day == today and not force_today)]
            for sl in past:
                if R.random() < p_cancel and not force_today:
                    sl.cancelled, sl.cancel_reason = True, "enseignant_absent"
            if perf < 0.6 and len(past) > 3:          # struggling wilaya: at least one teacher absence per group
                sl = R.choice(past[1:-1])
                sl.cancelled, sl.cancel_reason = True, "enseignant_absent"
            uncalled = {sl.id for sl in past if not sl.cancelled and R.random() < p_uncalled}
            past = [sl for sl in past if not sl.cancelled and sl.id not in uncalled]
            for e in g.enrollments:
                low = R.random() < max(0.03, 0.4 - 0.4 * perf)        # share of irregular trainees
                rel = min(0.995, max(0.4, R.gauss(0.68, 0.1) if low else R.gauss(0.95, 0.035)))
                stop = len(past) + 1
                if R.random() < 0.06 * (1.45 - perf):
                    stop = R.randint(2, max(2, len(past) - 2))
                for k, sl in enumerate(past):
                    if k >= stop:
                        st = "absent"
                    else:
                        r = R.random()
                        st = "present" if r < rel else ("excused" if r < rel + 0.04 else "absent")
                        if st == "present" and R.random() < 0.08:
                            st = "late"
                    arrived = None
                    if st == "late":
                        arrived = f"{int(sl.start[:2]):02d}:{R.choice([15, 20, 30, 40])}"
                    db.session.add(Attendance(slot=sl, enrollment=e, status=st, arrived=arrived, method="appel",
                                              marked_by_id=sl.teacher_id,
                                              marked_at=datetime.combine(sl.day, time(int(sl.start[:2]), 20))))
            for sl in past:
                sl.called_at = datetime.combine(sl.day, time(int(sl.start[:2]), 20))
        db.session.flush()
        s.status = "running" if status == "running" else "open"
        if status in ("closed", "validated", "submitted", "rejected"):
            close_day = s.ends_on + timedelta(days=R.randint(1, 4))
            T.close_session(s, today=close_day)
            if status != "closed":
                s.nesda_status = "submitted"
                s.nesda_submitted_at = datetime.combine(close_day, time(9))
            if status == "validated":
                nesda = User.query.filter_by(role="nesda", wilaya_id=inst.wilaya_id).first()
                s.nesda_status, s.nesda_w_by_id = "validated", nesda.id if nesda else None
                vday = close_day + timedelta(days=R.randint(3, 9))
                s.nesda_w_at = datetime.combine(vday, time(14))
                T.issue_certificates(s, today=vday)
                # satisfaction
                qs = SurveyQuestion.query.filter_by(active=True).order_by(SurveyQuestion.order).all()
                for e in s.enrollments:
                    if e.status == "confirmed" and not e.dropout and R.random() < 0.55 + 0.3 * perf:
                        base = 3.3 + 1.4 * perf
                        ans = {q.id: max(1, min(5, round(R.gauss(base, 0.8)))) for q in qs}
                        db.session.add(SurveyResponse(session=s, answers=json.dumps(ans), overall=ans[qs[-1].id],
                                                      comment=R.choice([None, None, None, "Très utile pour mon projet.",
                                                                        "Prévoir plus de cas pratiques.",
                                                                        "Horaires difficiles pour les stagiaires en entreprise.",
                                                                        "Merci aux enseignants."]),
                                                      created_at=datetime.combine(s.ends_on + timedelta(days=R.randint(1, 5)), time(18))))
                        e.survey_done = True
            if status == "rejected":
                nesda = User.query.filter_by(role="nesda", wilaya_id=inst.wilaya_id).first()
                s.nesda_status = "rejected"
                s.nesda_w_by_id = nesda.id if nesda else None
                s.nesda_note = "Appel manquant pour le créneau du module 2 (groupe G2) : merci de compléter puis de resoumettre."
        return s

    # previous year: everything closed and validated; current year: mixed statuses
    counter = 0
    for wcode, insts in insts_by_w.items():
        perf = PERF.get(wcode, 0.7)
        for i in insts:
            n_prev = max(2, round(4 * perf)) + (1 if wcode == "34" else 0)
            codes = R.sample([c for c, *_ in CATALOGUE], n_prev)
            for k, code in enumerate(codes):
                a, b = (p_s1 if k % 2 == 0 else p_s2)
                start = a + timedelta(days=R.randint(20, (b - a).days - 30))
                make_session(i, code, start, n_groups=R.choice([1, 2, 2, 3]) if perf > 0.7 else R.choice([1, 2]),
                             per_group=R.choice([14, 16, 18, 20]), perf=perf, status="validated")
                counter += 1
            # current year
            if (today - cur_start).days > 30:
                make_session(i, R.choice(["ENT-01", "ENT-03", "ENT-10"]), cur_start + timedelta(days=R.randint(8, 15)),
                             n_groups=R.choice([1, 2]), per_group=16, perf=perf,
                             status=R.choice(["validated", "validated", "submitted"]) if wcode != "34" else "validated")
                counter += 1
            if perf >= 0.8 or wcode == "34":
                make_session(i, R.choice(["ENT-02", "ENT-07"]), today - timedelta(days=R.randint(3, 8)),
                             n_groups=2, per_group=18, perf=perf, status="running")
                counter += 1

    # BBA-01 showcase: running session where the demo teacher calls the roll today,
    # one closed session waiting for NESDA validation, one rejected, one open for registrations
    bba01 = Institute.query.filter_by(code="INSFP-BBA-01").first()
    if bba01:
        boot = make_session(bba01, "ENT-09", today - timedelta(days=4), n_groups=2, per_group=18, perf=1.0,
                            status="running", force_today=True, mfirst_teacher=demo_teacher)
        if demo_teacher:   # the demo teacher always has today's roll call to take
            for g in boot.groups:
                for sl in g.slots:
                    if sl.day == today:
                        sl.teacher = demo_teacher
                        sl.module = next(m for m in boot.modules if m.supervisor_id == demo_teacher.id)
        make_session(bba01, "ENT-04", today - timedelta(days=24), n_groups=2, per_group=16, perf=0.95,
                     status="submitted", mfirst_teacher=demo_teacher)
        make_session(bba01, "ENT-06", today - timedelta(days=30), n_groups=1, per_group=16, perf=0.9,
                     status="rejected")
        # live demo: a running session whose slots are all past, ready to be closed and submitted to NESDA
        make_session(bba01, "ENT-02", today - timedelta(days=16), n_groups=1, per_group=14, perf=0.95,
                     status="running", mfirst_teacher=demo_teacher)
        make_session(bba01, "ENT-05", today + timedelta(days=12), n_groups=2, per_group=20, perf=1.0, status="open",
                     mfirst_teacher=demo_teacher)
        make_session(bba01, "ENT-08", today + timedelta(days=30), n_groups=1, per_group=20, perf=1.0, status="open")
        counter += 6
    for code in ("INSFP-BBA-02", "INSFP-ALG-01", "INSFP-ORN-01", "INSFP-STF-01"):
        i = Institute.query.filter_by(code=code).first()
        if i:
            make_session(i, R.choice(["ENT-07", "ENT-08", "ENT-10"]), today + timedelta(days=R.randint(8, 25)),
                         n_groups=1, per_group=20, perf=1.0, status="open")
            counter += 1
    db.session.flush()

    # ---------------- NESDA outcome (fictitious) for trained participants
    for p in people:
        started = any(a.status in ("present", "late") for e in p.enrollments for a in e.attendances)
        if not started:
            continue
        e = p.enrollments[0]
        if e.session.ends_on and e.session.ends_on < today - timedelta(days=60):
            perf = PERF.get(e.session.institute.wilaya.code, 0.7)
            r = R.random()
            if r < 0.06 * perf + 0.02:
                p.nesda_status = "abouti"
            elif r < 0.17 * perf + 0.04:
                p.nesda_status = "accepte"
            elif r < 0.35 * perf + 0.08:
                p.nesda_status = "depose"
            if p.nesda_status != "non_depose":
                p.nesda_status_on = e.session.ends_on + timedelta(days=R.randint(20, 120))
        elif e.session.status == "closed" and R.random() < 0.15:
            p.nesda_status, p.nesda_status_on = "depose", today - timedelta(days=R.randint(1, 10))
    db.session.flush()

    # ---------------- objectives
    def realised(wcode, label, sem):
        per = Period(label, {0: "A", 1: "S1", 2: "S2"}[sem])
        return K.kpis_for_institutes([i.id for i in insts_by_w[wcode]], per)

    data_codes = list(insts_by_w)
    for wcode in data_codes:
        w = wil[wcode]
        for sem in (1, 2, 0):
            vals = realised(wcode, prev_label, sem)
            for k, v in vals.items():
                if v is None:
                    continue
                pf = PERF.get(wcode, 0.7)
                f = R.choice([0.8, 0.85, 0.9, 0.95] if pf >= 1.0 else [1.25, 1.35, 1.5] if pf < 0.5 else
                             [0.85, 0.9, 0.95, 0.97, 1.0, 1.08] if pf >= 0.9 else
                             [0.9, 1.0, 1.08, 1.15] if pf >= 0.75 else [1.05, 1.15, 1.25, 1.35])
                tgt = (min(98.0, round(v * (2 - f) if k in K.LOWER_IS_BETTER else v * f)) if k in K.RATES
                       else max(1, round(v * (2 - f) if k in K.LOWER_IS_BETTER else v * f)))
                db.session.add(Objective(year=prev_label, semester=sem, wilaya_id=w.id, kpi=k, target=tgt))
    # current year: set at the opening of the training year for the 69 wilayas
    generic = {"groups": 8, "sessions": 4, "trained": 120, "teachers": 10, "hours": 1400, "fill": 80, "attendance": 85,
               "dropouts": 12, "dropout_rate": 10, "certificates": 95, "accepted": 15, "conversion": 12,
               "completed": 5, "satisfaction": 85, "response": 60}
    for w in wil.values():
        if w.code in data_codes:
            base = realised(w.code, prev_label, 0)
            grow = {"19": 0.6, "28": 1.5}.get(w.code, 1.1)    # Sétif ahead of its targets, M'Sila behind
            ann = {k: (generic[k] if base.get(k) is None else
                       (round(base[k]) if k in K.RATES else max(1, round(base[k] * grow)))) for k in K.KPIS}
            if w.code == "19":   # targets set realistically: Sétif is ahead
                ann.update({k: max(0, ann[k] - 6) for k in K.RATES if k not in K.LOWER_IS_BETTER and k in ann})
                ann.update({"dropout_rate": ann["dropout_rate"] + 6, "dropouts": ann["dropouts"] * 3})
            if w.code == "28":
                ann.update({"attendance": 90, "dropout_rate": 8, "satisfaction": 85, "fill": 85})
        else:
            ann = dict(generic)
        for k, v in ann.items():
            db.session.add(Objective(year=cur_label, semester=0, wilaya_id=w.id, kpi=k, target=v))
            s1 = v if k in K.RATES else max(1, round(v * 0.5))
            if k in ("accepted", "conversion", "completed"):
                continue                       # NESDA outcomes come months later: annual target only
            db.session.add(Objective(year=cur_label, semester=1, wilaya_id=w.id, kpi=k, target=s1))
            db.session.add(Objective(year=cur_label, semester=2, wilaya_id=w.id, kpi=k, target=s1))
    # BBA: DFEP distribution between its CDE (counts split, rates copied)
    bba_insts = insts_by_w["34"]
    weights = [0.45, 0.35, 0.20][:len(bba_insts)]
    for o in Objective.query.filter_by(year=cur_label, wilaya_id=wil["34"].id, institute_id=None).all():
        for i, wgt in zip(bba_insts, weights):
            v = o.target if o.kpi in K.RATES else max(1, round(o.target * wgt))
            db.session.add(Objective(year=cur_label, semester=o.semester, wilaya_id=o.wilaya_id, institute_id=i.id,
                                     kpi=o.kpi, target=v))
    db.session.flush()

    # ---------------- annual programmes
    for wcode, status, label in (("34", "validated", cur_label), ("34", "validated", prev_label),
                                 ("19", "submitted", cur_label), ("16", "draft", cur_label)):
        prog = Programme(wilaya_id=wil[wcode].id, year=label, status=status)
        db.session.add(prog)
        if status == "validated":
            prog.validated_by_id = User.query.filter_by(role="dfep", wilaya_id=wil[wcode].id).first().id
            prog.validated_at = datetime.combine(cur_start if label == cur_label else p_s1[0], time(10))
        for i in insts_by_w[wcode]:
            for code in R.sample([c for c, *_ in CATALOGUE], 4):
                db.session.add(ProgrammeLine(programme=prog, institute=i, template=tpls[code][0],
                                             semester=R.choice([1, 2]), planned_groups=R.choice([1, 2, 2, 3])))
    db.session.flush()

    # ---------------- semester reports of the previous year (frozen, transmitted)
    from .blueprints.reports import _snapshot_institute, _snapshot_wilaya
    for sem in (1, 2):
        per = Period(prev_label, f"S{sem}")
        when = datetime.combine(per.end + timedelta(days=10), time(10))
        for wcode in data_codes:
            w = wil[wcode]
            for i in insts_by_w[wcode]:
                resp = User.query.filter_by(institute_id=i.id, role="resp").first()
                db.session.add(Report(level="institute", institute_id=i.id, wilaya_id=w.id, year=prev_label,
                                      semester=sem, status="transmitted",
                                      snapshot=json.dumps(_snapshot_institute(i, per)), generated_at=when,
                                      transmitted_by_id=resp.id if resp else None, transmitted_at=when))
            db.session.flush()
            dfep = User.query.filter_by(role="dfep", wilaya_id=w.id).first()
            db.session.add(Report(level="wilaya", wilaya_id=w.id, year=prev_label, semester=sem, status="transmitted",
                                  snapshot=json.dumps(_snapshot_wilaya(w, per)), generated_at=when + timedelta(days=5),
                                  transmitted_by_id=dfep.id if dfep else None, transmitted_at=when + timedelta(days=5)))

    # ---------------- candidatures (formulaire en 4 étapes, modèle fp.cde.dz)
    from .models import Candidature, READINESS_Q
    IDEAS = ["Atelier de réparation de téléphones", "Pâtisserie traditionnelle", "Serre de légumes hors-sol",
             "Agence de développement web", "Menuiserie aluminium", "Élevage avicole", None, None]
    SECT = ["numerique", "artisanat", "agri", "numerique", "btp", "agri", "services", "commerce"]
    n_c = 0
    for wcode in ("34", "19", "28"):
        for i in insts_by_w.get(wcode, [])[:3]:
            n = 14 if i.code.endswith("01") and wcode == "34" else 6
            for k in range(n):
                sex = R.choice("FM")
                lvl = R.choice([0, 1, 1, 2, 2, 3])
                ans = {"discover": int(lvl == 0), "skills": int(lvl >= 1), "create_soon": int(lvl >= 2),
                       "project_ready": int(lvl == 3), "business": int(R.random() < .8), "initiative": int(R.random() < .85)}
                j = R.randrange(len(IDEAS))
                st = R.choice(["nouvelle"] * 5 + ["retenue"] * 2 + ["refusee"])
                c = Candidature(answers=",".join(f"{q}={ans[q]}" for q in READINESS_Q),
                                first_name=R.choice(F_FIRST if sex == "F" else M_FIRST), last_name=R.choice(LAST),
                                sex=sex, birth_date=date(R.randint(1996, 2006), R.randint(1, 12), R.randint(1, 28)),
                                phone=_phone(), wilaya_id=wil[wcode].id, pstatus=R.choice(["diplome", "diplome", "stagiaire"]),
                                origin_institute_id=i.id, specialty=R.choice(SPECIALTIES),
                                diploma_year=R.choice([2023, 2024, 2025, 2026]), idea=IDEAS[j] if lvl >= 2 else None,
                                sector=SECT[j], institute_id=i.id, consent_at=datetime.combine(today, time(9)),
                                status=st, note="Hors public cible (ni stagiaire ni diplômé de la FP)" if st == "refusee" else None,
                                created_at=datetime.combine(today - timedelta(days=R.randint(0, 20)), time(R.randint(8, 21), R.randint(0, 59))))
                db.session.add(c)
                n_c += 1
    db.session.commit()
    n_att = Attendance.query.count()
    return (f"seed-demo: {counter} sessions, {len(people)} participants, {n_att} présences, "
            f"{Objective.query.count()} objectifs, {Report.query.count()} rapports, {n_c} candidatures (données fictives)")


# ---------------------------------------------------------------- site public (événements, signalements)

def seed_site(today=None):
    """Événements et signalements FICTIFS pour le site public. Idempotent."""
    from .models import Event, Ticket
    today = today or date.today()
    if Event.query.first():
        return "seed-site: déjà présent"
    inst = {i.code: i for i in Institute.query}
    wil = {w.code: w for w in Wilaya.query}
    bba = Institute.query.join(Wilaya).filter(Wilaya.code == "34").order_by(Institute.code).first()
    EV = [
        # (jours, durée, kind, institut, wilaya, titre fr, titre ar, lieu, texte fr, texte ar)
        (6, 1, "portes_ouvertes", bba, None, "Journée portes ouvertes du CDE", "يوم الأبواب المفتوحة للمركز", "Hall principal",
         "Venez découvrir le CDE, rencontrer les enseignants et vous inscrire à la prochaine session.\nPrésentation des parcours, témoignages d'anciens stagiaires et stands NESDA.",
         "تعال لاكتشاف المركز ولقاء الأساتذة والتسجيل في الدورة القادمة.\nعرض المسارات وشهادات المتربصين السابقين وأجنحة الوكالة."),
        (12, 2, "salon", None, "16", "Salon national des jeunes entrepreneurs de la formation professionnelle", "الصالون الوطني للمقاولين الشباب للتكوين المهني", "Palais des expositions, Alger",
         "Les meilleurs projets issus des CDE de toutes les wilayas exposent leurs produits et services.\nAteliers de financement animés par la NESDA.",
         "تعرض أفضل المشاريع الناتجة عن المراكز من كل الولايات منتجاتها وخدماتها.\nورشات تمويل تنشطها الوكالة."),
        (20, 1, "concours", None, None, "Concours national « Mon projet en 3 minutes »", "المسابقة الوطنية «مشروعي في 3 دقائق»", "Dans chaque CDE puis finale nationale",
         "Présentez votre projet en trois minutes devant un jury. Les lauréats de wilaya participent à la finale nationale.",
         "قدم مشروعك في ثلاث دقائق أمام لجنة تحكيم. يشارك الفائزون على مستوى الولايات في النهائي الوطني."),
        (3, 1, "annonce", inst.get("INSFP-STF-01"), None, "Ouverture des inscriptions — session de novembre", "فتح التسجيل — دورة نوفمبر", None,
         "Les inscriptions pour la session de novembre sont ouvertes. 150 places, groupes du matin et de l'après-midi.",
         "التسجيل في دورة نوفمبر مفتوح. 150 مقعدا، أفواج صباحية ومسائية."),
        (9, 1, "evenement", inst.get("INSFP-ORN-01"), None, "Atelier « Financer son projet avec la NESDA »", "ورشة «تمويل مشروعك مع الوكالة»", "Salle de conférences",
         "Les conseillers NESDA présentent les dispositifs de financement et répondent aux questions des porteurs de projet.",
         "يقدم مستشارو الوكالة أجهزة التمويل ويجيبون عن أسئلة حاملي المشاريع."),
        (15, 1, "portes_ouvertes", inst.get("INSFP-CST-01"), None, "Portes ouvertes CDE Constantine", "أبواب مفتوحة لمركز قسنطينة", None,
         "Visite du centre, présentation du programme et inscriptions sur place.", "زيارة المركز وعرض البرنامج والتسجيل في عين المكان."),
        (-20, 1, "evenement", bba, None, "Remise des attestations — session d'octobre", "تسليم الشهادات — دورة أكتوبر", "Amphithéâtre",
         "Cérémonie de remise des attestations par le représentant de la NESDA.", "حفل تسليم الشهادات من طرف ممثل الوكالة."),
    ]
    for d, dur, kind, i, wcode, tf, ta, place, bf, ba in EV:
        start = today + timedelta(days=d)
        w = i.wilaya if i else wil.get(wcode) if wcode else None
        db.session.add(Event(kind=kind, title_fr=tf, title_ar=ta, body_fr=bf, body_ar=ba, starts_on=start,
                             ends_on=start + timedelta(days=dur - 1) if dur > 1 else None, place=place,
                             wilaya=w, institute=i, published=True))
    TK = [
        ("inscription", "Amine B.", "0550000001", None, bba, "Erreur dans mon numéro de téléphone",
         "J'ai saisi un mauvais numéro lors de mon inscription, le bon est 0550000001.", "open"),
        ("compte", "Enseignant CDE", None, "formateur@example.dz", bba, "Mot de passe oublié",
         "Je n'arrive plus à me connecter pour faire l'appel.", "progress"),
        ("attestation", "Sara K.", "0660000002", None, inst.get("INSFP-STF-01"), "Attestation non reçue",
         "J'ai terminé la session d'octobre, quand puis-je récupérer mon attestation ?", "resolved"),
        ("technique", "Yacine M.", "0770000003", None, None, "La page d'inscription ne s'affiche pas",
         "Sur mon téléphone, la page reste blanche après l'étape 2.", "open"),
    ]
    for cat, name, ph, em, i, sj, msg, st in TK:
        tk = Ticket(category=cat, name=name, phone=ph, email=em, institute=i, wilaya=i.wilaya if i else None,
                    subject=sj, message=msg, status=st)
        if st == "resolved":
            tk.reply = "Votre attestation est disponible auprès du représentant NESDA de la wilaya depuis le 20 du mois."
        db.session.add(tk)
    db.session.commit()
    return f"seed-site: {len(EV)} événements, {len(TK)} signalements"

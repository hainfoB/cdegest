"""Command line: `flask --app wsgi seed-base` (idempotent, safe to run at every deploy)."""
import os
from datetime import date

import click

from .extensions import db
from .models import Institute, User, Wilaya

from .data_wilayas import WILAYAS_69

# Wilayas whose demo data are fictitious (BBA is the pilot wilaya)
DEMO_WILAYAS = {"19", "28"}

INSTITUTES = [
    # code, wilaya, fr, ar
    ("INSFP-BBA-01", "34", "INSFP Bordj Bou Arréridj 01", "المعهد الوطني المتخصص في التكوين المهني برج بوعريريج 01"),
    ("INSFP-BBA-02", "34", "INSFP Bordj Bou Arréridj 02", "المعهد الوطني المتخصص في التكوين المهني برج بوعريريج 02"),
    ("INSFP-STF-01", "19", "INSFP Sétif 01", "المعهد الوطني المتخصص في التكوين المهني سطيف 01"),
    ("INSFP-STF-02", "19", "INSFP Sétif 02", "المعهد الوطني المتخصص في التكوين المهني سطيف 02"),
    ("INSFP-MSL-01", "28", "INSFP M'Sila 01", "المعهد الوطني المتخصص في التكوين المهني المسيلة 01"),
]

# show = displayed on the demo login page
DEMO_USERS = [
    {"email": "admin@cdegest.dz", "name": "Administrateur plateforme", "role": "admin", "show": False},
    {"email": "mfep@cdegest.dz", "name": "Direction centrale MFEP", "role": "mfep", "show": True},
    {"email": "dfep.bba@cdegest.dz", "name": "DFEP Bordj Bou Arréridj", "role": "dfep", "wilaya": "34", "show": True, "scope": {'ar': 'برج بوعريريج', 'fr': 'BBA', 'en': 'BBA'}},
    {"email": "coord.bba@cdegest.dz", "name": "Coordinateur CDE BBA", "role": "coord", "wilaya": "34", "show": True, "scope": {'ar': 'برج بوعريريج', 'fr': 'BBA', 'en': 'BBA'}},
    {"email": "resp.insfp-bba01@cdegest.dz", "name": "Responsable CDE INSFP BBA 01", "role": "resp", "institute": "INSFP-BBA-01", "show": True, "scope": {'ar': 'المعهد BBA 01', 'fr': 'INSFP BBA 01', 'en': 'INSFP BBA 01'}},
    {"email": "formateur.bba01@cdegest.dz", "name": "Enseignant INSFP BBA 01", "role": "formateur", "institute": "INSFP-BBA-01", "show": True, "scope": {'ar': 'المعهد BBA 01', 'fr': 'INSFP BBA 01', 'en': 'INSFP BBA 01'}},
    {"email": "resp.insfp-bba02@cdegest.dz", "name": "Responsable CDE INSFP BBA 02", "role": "resp", "institute": "INSFP-BBA-02", "show": False},
    {"email": "dfep.setif@cdegest.dz", "name": "DFEP Sétif", "role": "dfep", "wilaya": "19", "show": False},
    {"email": "coord.setif@cdegest.dz", "name": "Coordinateur CDE Sétif", "role": "coord", "wilaya": "19", "show": False},
    {"email": "dfep.msila@cdegest.dz", "name": "DFEP M'Sila", "role": "dfep", "wilaya": "28", "show": False},
]


def seed_base(demo=True, password=None):
    created = 0
    by_code = {}
    for code, fr, ar in WILAYAS_69:
        w = Wilaya.query.filter_by(code=code).first()
        if not w:
            w = Wilaya(code=code, name_fr=fr, name_ar=ar, is_demo=demo and code in DEMO_WILAYAS)
            db.session.add(w)
            created += 1
        by_code[code] = w
    db.session.flush()

    insts = {}
    for code, wcode, fr, ar in INSTITUTES:
        i = Institute.query.filter_by(code=code).first()
        if not i:
            i = Institute(code=code, wilaya=by_code[wcode], name_fr=fr, name_ar=ar, cde_opened_on=date(2025, 10, 1))
            db.session.add(i)
            created += 1
        insts[code] = i
    db.session.flush()

    users = DEMO_USERS if demo else DEMO_USERS[:1]
    for spec in users:
        if User.query.filter_by(email=spec["email"]).first():
            continue
        u = User(email=spec["email"], name=spec["name"], role=spec["role"], lang="ar")
        if "wilaya" in spec:
            u.wilaya = by_code[spec["wilaya"]]
        if "institute" in spec:
            u.institute = insts[spec["institute"]]
            u.wilaya = insts[spec["institute"]].wilaya
        pwd = password if spec["role"] != "admin" else os.environ.get("ADMIN_PASSWORD", password)
        u.set_password(pwd)
        db.session.add(u)
        created += 1
    db.session.commit()
    return created


def register_cli(app):
    @app.cli.command("seed-base")
    def seed_base_cmd():
        """Wilayas, institutes and (in demo mode) demo accounts. Idempotent."""
        n = seed_base(demo=app.config["DEMO_MODE"], password=app.config["DEMO_PASSWORD"])
        click.echo(f"seed-base: {n} élément(s) créé(s)")

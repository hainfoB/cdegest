import pytest

from app import create_app
from app.cli import seed_base
from app.config import TestConfig
from app.extensions import db

PWD = "Cde@2026"


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        seed_base(demo=True, default_password=PWD)
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def nin_of(email):
    from app.cli import BY_EMAIL
    return BY_EMAIL[email]["nin"] if email in BY_EMAIL else email


def last_code(user_id):
    """Code tel qu'il figure dans le message simulé M-01 (boîte d'envoi)."""
    import re
    from app.models import Notification
    n = Notification.query.filter_by(code="M-01", user_id=user_id).order_by(Notification.id.desc()).first()
    return re.search(r"(\d{6})", n.body).group(1) if n else None


def login(client, email, password=PWD, role=None):
    """Connexion complète : NIN + mot de passe, code à usage unique, choix du rôle (le premier par défaut)."""
    from flask import g
    from app.models import User
    g.pop("_login_user", None)
    nin = nin_of(email)
    r = client.post("/login", data={"nin": nin, "password": password}, follow_redirects=False)
    if r.status_code != 302:
        return r
    if r.headers["Location"].endswith("/login/code"):
        u = User.by_nin(nin)
        r = client.post("/login/code", data={"code": last_code(u.id)}, follow_redirects=False)
    if "/login/role" in r.headers.get("Location", ""):
        u = User.by_nin(nin)
        habs = u.valid_habilitations()
        h = next((x for x in habs if x.role == role), None) if role else None
        if h is None:
            from app.cli import BY_EMAIL
            first = BY_EMAIL.get(email, {}).get("roles", [(habs[0].role, None)])[0][0]
            h = next((x for x in habs if x.role == first), habs[0])
        r = client.post("/login/role", data={"hab": h.id}, follow_redirects=False)
    return r


def make_user(name, role, institute=None, wilaya=None, nin=None, password="x" * 12, email=None):
    """Compte de test avec une habilitation (NIN fictif unique si non fourni)."""
    import itertools
    from app.extensions import db
    from app.models import User
    from app.utils import utcnow
    nin = nin or f"1888{next(_SEQ):014d}"
    u = User(name=name, email=email or f"{nin}@test.dz", phone="0550112233", charter_at=utcnow(), identity_source="simule")
    u.nin = nin
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    u.grant(role, institute=institute, wilaya=wilaya)
    db.session.commit()
    return u


import itertools as _it  # noqa: E402
_SEQ = _it.count(101)


def sim_birth(nin):
    from app.services import connectors as C
    return C.identity(nin)[1]["date_naissance"]


def pub_register(pub, slug, k, phone=None, password="Mot-de-passe-1"):
    """Inscription publique depuis le catalogue avec un NIN fictif ; renvoie l'inscription créée."""
    from flask import g
    from app.models import Enrollment, Participant
    from app import nin as NIN
    g.pop("_login_user", None)          # le contexte d'application des tests est partagé entre clients
    nin = f"1777{k:014d}"
    r = pub.post(f"/formations/{slug}", data={"nin": nin, "birth_date": sim_birth(nin), "phone": phone or f"055500{k:04d}",
                                               "email": f"p{k}@test.dz", "consent": "1", "wilaya": "34", "mobile": "sms",
                                               "password": password, "password2": password})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    g.pop("_login_user", None)
    p = Participant.query.filter_by(nin_hash=NIN.fingerprint(nin)).first()
    return Enrollment.query.filter_by(participant_id=p.id).order_by(Enrollment.id.desc()).first()

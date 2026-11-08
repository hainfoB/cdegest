"""CDC v1.3 : connexion par NIN, code à usage unique, habilitations multiples, messages, échanges avec l'État."""
import re
from datetime import date, datetime, timedelta

import pytest
from flask import g

from app.extensions import db
from app.models import ApiCall, AuditLog, Habilitation, Institute, Notification, OtpCode, Session, User
from tests.conftest import PWD, last_code, login, make_user, nin_of, pub_register

RESP, TEACH, NESDA_W = "resp.insfp-bba01@cdegest.dz", "formateur.bba01@cdegest.dz", "nesda.bba@cdegest.dz"


def _u(email):
    return User.by_nin(nin_of(email))


# ------------------------------------------------------------------ connexion (CU-01, ES-11)

def test_login_is_by_nin_and_agents_always_get_a_code(client):
    u = _u("mfep@cdegest.dz")
    r = client.post("/login", data={"nin": u.nin, "password": PWD})
    assert r.headers["Location"].endswith("/login/code")
    assert client.get("/tableau-de-bord").status_code == 302, "not logged in before the code"
    otp = OtpCode.query.filter_by(user_id=u.id).one()
    assert abs((otp.expires_at - otp.created_at).total_seconds() - 300) < 2 and len(otp.code_hash) > 20
    msg = Notification.query.filter_by(code="M-01", user_id=u.id).one()
    assert "http" not in msg.body, "no link in a code message (RG-50)"
    assert client.post("/login/code", data={"code": "000000"}).status_code == 200
    r = client.post("/login/code", data={"code": last_code(u.id)})
    assert r.headers["Location"].endswith("/tableau-de-bord")


def test_email_is_not_an_identifier_anymore(client):
    assert client.post("/login", data={"nin": "mfep@cdegest.dz", "password": PWD}).status_code == 200


def test_code_locks_after_five_wrong_attempts(client):
    u = _u("mfep@cdegest.dz")
    client.post("/login", data={"nin": u.nin, "password": PWD})
    good = last_code(u.id)
    for _ in range(5):
        client.post("/login/code", data={"code": "111111" if good != "111111" else "222222"})
    r = client.post("/login/code", data={"code": good})
    assert r.status_code == 200, "the right code no longer works after 5 failures"


def test_code_expires_after_five_minutes(app, client):
    u = _u("mfep@cdegest.dz")
    client.post("/login", data={"nin": u.nin, "password": PWD})
    otp = OtpCode.query.filter_by(user_id=u.id).one()
    otp.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert client.post("/login/code", data={"code": last_code(u.id)}).status_code == 200


def test_at_most_three_codes_per_quarter_hour(client):
    u = _u("mfep@cdegest.dz")
    client.post("/login", data={"nin": u.nin, "password": PWD})
    for _ in range(4):
        client.post("/login/code", data={"action": "resend", "channel": "email"})
    assert OtpCode.query.filter_by(user_id=u.id).count() == 3


def test_account_locked_after_five_wrong_passwords(client):
    u = _u("coord.bba@cdegest.dz")
    for _ in range(5):
        client.post("/login", data={"nin": u.nin, "password": "wrong"})
    db.session.refresh(u)
    assert u.locked
    r = client.post("/login", data={"nin": u.nin, "password": PWD})
    assert r.status_code == 200 and "/login/code" not in r.headers.get("Location", "")


# ------------------------------------------------------------------ plusieurs rôles (RG-34, RG-35)

def test_person_with_two_roles_chooses_and_only_has_the_active_role(client):
    u = _u(RESP)
    assert {h.role for h in u.valid_habilitations()} == {"resp", "formateur"}
    r = client.post("/login", data={"nin": u.nin, "password": PWD})
    r = client.post("/login/code", data={"code": last_code(u.id)})
    assert "/login/role" in r.headers["Location"]
    teach = next(h for h in u.habilitations if h.role == "formateur")
    resp = next(h for h in u.habilitations if h.role == "resp")
    client.post("/login/role", data={"hab": teach.id})
    assert client.get("/candidatures/").status_code == 403, "the teacher role does not carry the manager's rights"
    assert client.get("/mes-creneaux").status_code == 200
    client.post("/role", data={"hab": resp.id})
    assert client.get("/candidatures/").status_code == 200
    assert AuditLog.query.filter_by(action="role.switch").count() == 1
    assert AuditLog.query.filter(AuditLog.role == "resp").count() >= 1, "the journal records the active role"


def test_cannot_switch_to_a_role_of_someone_else(client):
    login(client, RESP)
    other = Habilitation.query.filter_by(role="mfep").first()
    assert client.post("/role", data={"hab": other.id}).status_code == 403


# ------------------------------------------------------------------ habilitations (CU-02)

def test_resp_grants_teacher_by_nin_then_the_person_activates(app, client):
    login(client, RESP)
    nin = "155500000000000123"
    r = client.post("/comptes", data={"action": "grant", "nin": nin, "role": "formateur",
                                      "institute": Institute.query.filter_by(code="INSFP-BBA-01").first().id,
                                      "reason": "Affectation", "email": "new.teacher@test.dz", "name": "Mme Test"})
    assert r.status_code == 302
    u = User.by_nin(nin)
    h = u.habilitations[0]
    assert h.status == "pending" and h.granted_by.nin == _u(RESP).nin and u.invite_token
    invite = Notification.query.filter_by(code="M-03", user_id=u.id, channel="email").one()
    assert "/activation/" in invite.body
    # a manager cannot grant a role outside table 5.1
    r = client.post("/comptes", data={"action": "grant", "nin": "155500000000000124", "role": "dfep", "reason": "x",
                                      "email": "x@test.dz"})
    assert User.by_nin("155500000000000124") is None
    # activation by the invited person
    pub = app.test_client()
    g.pop("_login_user", None)
    r = pub.post(f"/activation/{u.invite_token}", data={"channel": "email", "password": "Tres-long-123", "password2": "Tres-long-123",
                                                       "charter": "1"})
    assert r.headers["Location"].endswith("/login/code")
    r = pub.post("/login/code", data={"code": last_code(u.id)})
    db.session.refresh(u)
    assert u.charter_at and u.invite_token is None and u.habilitations[0].status == "active"


def test_revoked_role_stops_at_the_next_request(client):
    t = _u(TEACH)
    login(client, TEACH)
    assert client.get("/mes-creneaux").status_code == 200
    for h in t.habilitations:
        h.status = "revoked"
    db.session.commit()
    g.pop("_login_user", None)
    r = client.get("/mes-creneaux")
    assert r.status_code in (302, 403)


def test_revoke_needs_a_reason_and_notifies(client):
    login(client, RESP)
    h = next(x for x in _u(TEACH).habilitations if x.institute and x.institute.code == "INSFP-BBA-01")
    client.post("/comptes", data={"action": "revoke", "id": h.id})
    db.session.refresh(h)
    assert h.status == "active", "no reason, no change"
    client.post("/comptes", data={"action": "revoke", "id": h.id, "why": "Fin de mission"})
    db.session.refresh(h)
    assert h.status == "revoked" and h.change_reason == "Fin de mission"
    assert Notification.query.filter_by(code="M-03", user_id=h.user_id).count() >= 1


# ------------------------------------------------------------------ séparation des fonctions (RG-36)

def test_nesda_representative_cannot_validate_a_cde_where_he_has_another_role(app, client):
    from tests.test_flow import _session_with_today_slot
    from app.models import WorkshopTemplate
    tpl = WorkshopTemplate(code="T-02", theme="x", title_fr="X", title_ar="س", hours=3)
    db.session.add(tpl)
    db.session.commit()
    s = _session_with_today_slot(client, tpl)
    s.status, s.nesda_status = "closed", "submitted"
    n = _u(NESDA_W)
    n.grant("formateur", institute=s.institute)
    db.session.commit()
    client.post("/logout")
    login(client, NESDA_W, role="nesda")
    client.post(f"/nesda/sessions/{s.id}", data={"action": "validate"})
    db.session.refresh(s)
    assert s.nesda_status == "submitted"


# ------------------------------------------------------------------ messages (EP-11)

def test_quiet_hours_postpone_file_messages_but_not_codes(app, monkeypatch):
    from app.services import notify as N
    monkeypatch.setattr(N, "local_now", lambda: datetime(2026, 11, 7, 22, 30))
    u = _u("candidat.demo@cdegest.dz")
    r = N.recipient(u)
    b = N.send("M-04", r, {"ref": "CDE34-00001"}, "t:quiet")
    assert all(m.status == "scheduled" and m.scheduled_for.hour == 7 for m in b), "08:00 Algiers = 07:00 UTC"
    a = N.send("M-01", r, {"code": "123456"}, "t:code", channel="email")
    assert a[0].status == "delivered"


def test_daily_cap_and_one_message_per_event(app, monkeypatch):
    from app.services import notify as N
    monkeypatch.setattr(N, "local_now", lambda: datetime(2026, 11, 7, 10, 0))
    r = N.recipient(_u("candidat.demo@cdegest.dz"))
    for k in range(3):
        N.send("M-04", r, {"ref": f"R{k}"}, f"t:cap{k}")
    mob = Notification.query.filter(Notification.event_key.like("t:cap%"), Notification.channel != "email").order_by(Notification.id).all()
    assert [m.status for m in mob] == ["delivered", "delivered", "scheduled"], "RG-48 : 2 mobile messages per day"
    assert N.send("M-04", r, {"ref": "R0"}, "t:cap0") == [], "RG-50 : never twice the same event"


def test_unreachable_number_falls_back_to_email(app, monkeypatch):
    from app.services import notify as N
    monkeypatch.setattr(N, "local_now", lambda: datetime(2026, 11, 7, 10, 0))
    r = {"user": None, "user_id": None, "name": "A", "email": "a@test.dz", "phone": "0550000000", "whatsapp": None,
         "mobile": "sms", "wa_ok": False, "lang": "fr", "reminders": True}
    N.send("M-09", r, {"start": "10/11"}, "t:fallback")
    rows = {m.channel: m.status for m in Notification.query.filter_by(event_key="t:fallback")}
    assert rows == {"sms": "failed", "email": "delivered"}


def test_reminders_can_be_turned_off_but_not_file_messages(app):
    from app.services import notify as N
    u = _u("candidat.demo@cdegest.dz")
    u.reminders = False
    db.session.commit()
    assert N.send("M-09", N.recipient(u), {}, "t:rem") == []


def test_messages_never_contain_a_nin_or_birth_date(app, client):
    from tests.test_flow import _session_with_today_slot
    from app.models import WorkshopTemplate
    tpl = WorkshopTemplate(code="T-03", theme="x", title_fr="X", title_ar="س", hours=3)
    db.session.add(tpl)
    db.session.commit()
    s = _session_with_today_slot(client, tpl)
    e = pub_register(app.test_client(), s.slug, 7)
    p = e.participant
    for m in Notification.query.all():
        assert p.nin not in m.body and (p.birth_date.isoformat() not in m.body)
        assert not re.search(r"\b\d{18}\b", m.body)


# ------------------------------------------------------------------ échanges avec l'État (EP-12)

def test_connector_modes(app):
    from app.services import connectors as C
    st, data, src = C.identity("177700000000000555")
    assert st == "trouve" and src == "simule", "simulated data is never 'verified' (RG-41)"
    assert C.identity("177700000000009999")[0] == "indisponible"
    assert C.identity("177700000000000000")[0] == "inconnu"
    C.set_mode("etat_civil", "desactive", None)
    assert C.identity("177700000000000555")[0] == "desactive"
    C.set_mode("etat_civil", "reel", None)
    assert C.identity("177700000000000555")[2] == "declaratif", "real mode without agreement = degraded mode"
    calls = ApiCall.query.all()
    assert calls and all(c.nin_hash and "177700" not in (c.nin_hash or "") for c in calls), "NIN never stored in clear"


def test_registration_still_works_when_the_registry_is_down(app, client):
    from app.services import connectors as C
    from tests.test_flow import _session_with_today_slot
    from app.models import WorkshopTemplate, Participant
    tpl = WorkshopTemplate(code="T-04", theme="x", title_fr="X", title_ar="س", hours=3)
    db.session.add(tpl)
    db.session.commit()
    s = _session_with_today_slot(client, tpl)
    C.set_mode("etat_civil", "desactive", None)
    db.session.commit()
    pub = app.test_client()
    g.pop("_login_user", None)
    nin = "177700000000000321"
    r = pub.post(f"/formations/{s.slug}", data={"nin": nin, "birth_date": "2001-05-04", "last_name": "Declare", "first_name": "Nom",
                                               "phone": "0550111222", "email": "d@test.dz", "consent": "1", "password": "Mot-de-passe-1",
                                               "password2": "Mot-de-passe-1"})
    assert r.status_code == 302
    p = Participant.query.filter_by(last_name="Declare").one()
    assert p.identity_source == "declaratif"


def test_output_apis_need_a_partner_key(app, client):
    assert client.get("/api/v1/nesda/formes").status_code == 404, "closed while no key is configured"
    app.config["NESDA_API_KEY"] = "k-nesda"
    assert client.get("/api/v1/nesda/formes", headers={"X-Api-Key": "bad"}).status_code == 401
    r = client.get("/api/v1/nesda/formes?depuis=2020-01-01", headers={"X-Api-Key": "k-nesda"})
    assert r.status_code == 200 and "formes" in r.get_json()
    r = client.post("/api/v1/nesda/suites", json=[{"nin": "x", "numero_attestation": "none", "etat": "accepte"}],
                    headers={"X-Api-Key": "k-nesda"})
    assert r.get_json() == {"recus": 1, "appliques": 0}, "unknown certificate or NIN mismatch is ignored"
    app.config["MFEP_API_KEY"] = "k-mfep"
    r = client.get("/api/v1/mfep/statistiques", headers={"X-Api-Key": "k-mfep"})
    assert r.status_code == 200 and len(r.get_json()["wilayas"]) >= 1


def test_candidate_space_shows_demands_and_messages(app, client):
    login(client, "candidat.demo@cdegest.dz")
    assert client.get("/tableau-de-bord").status_code in (200, 302)
    r = client.get("/mon-espace/?lang=fr")
    assert r.status_code == 200 and "Mes demandes" in r.get_data(as_text=True)
    assert client.get("/candidatures/").status_code == 403


def test_demand_indicators(app):
    from app.models import Candidature
    from app.services import kpi as K
    from app.services.period import Period
    i = Institute.query.filter_by(code="INSFP-BBA-01").first()
    now = datetime.utcnow()
    for k, src in enumerate(["etat_civil", "simule", "etat_civil", "declaratif"]):
        c = Candidature(last_name="A", first_name="B", phone=f"05500000{k}1", institute_id=i.id, wilaya_id=i.wilaya_id,
                        identity_source=src, created_at=now - timedelta(days=4), status="orientee" if k < 2 else "nouvelle",
                        reviewed_at=now - timedelta(days=4 - (k + 1) * 1) if k < 2 else None, answers="")
        db.session.add(c)
    db.session.commit()
    v = K.kpis_for_institutes([i.id], Period(None, "A"))
    assert v["demands"] == 4 and v["verified"] == 50.0 and v["decision_days"] == 1.5


def test_login_error_speaks_of_nin(client):
    client.get("/lang/fr")
    r = client.post("/login", data={"nin": "177700000000000001", "password": "faux-mot-de-passe"})
    assert "NIN ou mot de passe incorrect" in r.get_data(as_text=True)


def test_programme_year_list_keeps_the_displayed_year(client):
    from app.services.period import recent_years
    login(client, "coord.bba@cdegest.dz")
    y0 = int(recent_years(1)[0][:4]) + 1
    nxt = f"{y0}-{y0 + 1}"
    html = client.get(f"/programme?y={nxt}").get_data(as_text=True)
    assert f"<option selected>{nxt}</option>" in html
    far = f"{y0 + 3}-{y0 + 4}"
    html = client.get(f"/programme?y={far}").get_data(as_text=True)
    assert f"<option selected>{far}</option>" in html

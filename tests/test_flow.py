"""End-to-end business flow: session → public registration → roll call → close → NESDA → certificate."""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Enrollment, Institute, Session, Slot, SurveyQuestion, User, WorkshopTemplate
from tests.conftest import login

RESP, TEACH, NESDA_W, DG = ("resp.insfp-bba01@cdegest.dz", "formateur.bba01@cdegest.dz",
                            "nesda.bba@cdegest.dz", "dg.nesda@cdegest.dz")


@pytest.fixture()
def tpl(app):
    t = WorkshopTemplate(code="T-01", theme="Idée", title_fr="Idée", title_ar="الفكرة", hours=6)
    db.session.add(t)
    db.session.add(SurveyQuestion(order=1, text_fr="Global", text_ar="عام", text_en="Overall", is_overall=True))
    db.session.commit()
    return t


def _session_with_today_slot(client, tpl):
    login(client, RESP)
    today = date.today()
    r = client.post("/sessions/nouvelle", data={"template": tpl.id, "title": "Atelier test", "starts_on": today.isoformat(),
                                                "ends_on": today.isoformat(), "seats_per_group": 3, "min_attendance": 80,
                                                "auto_confirm": "1", "mode": "hybrid"})
    assert r.status_code == 302
    s = Session.query.filter_by(title="Atelier test").first()
    teacher = User.query.filter_by(email=TEACH).first()
    other = User(email="ens2@x.dz", name="Ens 2", role="formateur", institute_id=s.institute_id)
    other.set_password("x" * 12)
    db.session.add(other)
    db.session.commit()
    client.post(f"/sessions/{s.id}/modules", data={"title": "M1", "hours": 3, "supervisor": teacher.id})
    # rule: a teacher without a supervised module cannot be given a slot
    client.post(f"/sessions/{s.id}/creneaux", data={"module": s.modules[0].id, "teacher": other.id, "day": today.isoformat(),
                                                    "start": "09:00", "end": "12:00", "groups": [s.groups[0].id]})
    assert Slot.query.count() == 0
    client.post(f"/sessions/{s.id}/creneaux", data={"module": s.modules[0].id, "teacher": teacher.id, "day": today.isoformat(),
                                                    "start": "09:00", "end": "12:00", "groups": [s.groups[0].id]})
    assert Slot.query.count() == 1
    client.post(f"/sessions/{s.id}/action", data={"action": "open"})
    db.session.refresh(s)
    assert s.status == "open"
    return s


def test_full_flow(app, client, tpl):
    s = _session_with_today_slot(client, tpl)
    pub = app.test_client()
    tokens = []
    for k in range(4):
        r = pub.post(f"/formations/{s.slug}", data={"last_name": f"Nom{k}", "first_name": "P", "phone": f"055500000{k}",
                                                   "consent": "1", "wilaya": "34"})
        assert r.status_code == 302
        tokens.append(r.headers["Location"].rsplit("/", 1)[-1])
    enrs = Enrollment.query.filter_by(session_id=s.id).order_by(Enrollment.id).all()
    assert [e.status for e in enrs] == ["confirmed", "confirmed", "confirmed", "waitlist"], "3 seats then waiting list"
    assert pub.get(f"/t/{tokens[0]}").status_code == 200

    # teacher calls the roll today
    client.post("/logout")
    login(client, TEACH)
    slot = Slot.query.first()
    data = {f"st_{e.id}": "present" for e in enrs[:2]}
    data[f"st_{enrs[2].id}"] = "absent"
    assert client.post(f"/appel/{slot.id}", data=data).status_code == 302
    assert slot.called_at is not None
    # teacher cannot close or manage the session
    assert client.post(f"/sessions/{s.id}/action", data={"action": "close"}).status_code == 403

    # CDE closes and submits to NESDA
    client.post("/logout")
    login(client, RESP)
    client.post(f"/sessions/{s.id}/action", data={"action": "start"})
    client.post(f"/sessions/{s.id}/action", data={"action": "close"})
    db.session.refresh(s)
    assert s.status == "closed"
    # certificates are locked before NESDA validation
    assert client.get(f"/sessions/{s.id}/attestations").status_code == 403
    client.post(f"/sessions/{s.id}/action", data={"action": "submit_nesda"})
    db.session.refresh(s)
    assert s.nesda_status == "submitted"

    # NESDA of another wilaya cannot see it; NESDA BBA validates
    client.post("/logout")
    login(client, NESDA_W)
    assert client.post(f"/nesda/sessions/{s.id}", data={"action": "validate"}).status_code == 302
    db.session.refresh(s)
    assert s.nesda_status == "validated"
    certified = [e for e in Enrollment.query.filter_by(session_id=s.id) if e.cert_no]
    assert len(certified) == 2, "only participants with attendance >= 80 %"

    # certificate printable at the CDE, verifiable publicly, survey available
    client.post("/logout")
    login(client, RESP)
    html = client.get(f"/sessions/{s.id}/attestations").get_data(as_text=True)
    assert certified[0].cert_no in html and "<svg" in html
    assert "authentique" in pub.get(f"/verifier/{certified[0].cert_no}?lang=fr").get_data(as_text=True)
    q = SurveyQuestion.query.first()
    r = pub.post(f"/t/{certified[0].token}/satisfaction", data={f"q{q.id}": "5", "comment": "Bien"})
    assert r.status_code == 302 and db.session.get(Enrollment, certified[0].id).survey_done


def test_teacher_cannot_call_another_day(app, client, tpl):
    s = _session_with_today_slot(client, tpl)
    slot = Slot.query.first()
    slot.day = date.today() - timedelta(days=1)
    db.session.commit()
    client.post("/logout")
    login(client, TEACH)
    assert client.post(f"/appel/{slot.id}", data={}).status_code == 403
    # the CDE manager can still correct, and it is flagged
    client.post("/logout")
    pub = app.test_client()
    pub.post(f"/formations/{s.slug}", data={"last_name": "X", "first_name": "Y", "phone": "0666000000", "consent": "1"})
    e = Enrollment.query.first()
    login(client, RESP)
    client.post(f"/appel/{slot.id}", data={f"st_{e.id}": "present"})
    assert e.attendances[0].corrected


def test_nesda_other_wilaya_forbidden(app, client, tpl):
    s = _session_with_today_slot(client, tpl)
    s.status, s.nesda_status = "closed", "submitted"
    db.session.commit()
    other = User(email="nesda.x@x.dz", name="N", role="nesda", wilaya_id=Institute.query.filter_by(code="INSFP-STF-01").first().wilaya_id)
    other.set_password("x" * 12)
    db.session.add(other)
    db.session.commit()
    client.post("/logout")
    client.post("/login", data={"email": "nesda.x@x.dz", "password": "x" * 12})
    assert client.post(f"/nesda/sessions/{s.id}", data={"action": "validate"}).status_code == 403


def test_dg_second_validation(app, client, tpl):
    app.config["NESDA_DG_VALIDATION"] = True
    s = _session_with_today_slot(client, tpl)
    s.status, s.closed_at, s.nesda_status = "closed", date.today(), "submitted"
    db.session.commit()
    client.post("/logout")
    login(client, NESDA_W)
    client.post(f"/nesda/sessions/{s.id}", data={"action": "validate"})
    db.session.refresh(s)
    assert s.nesda_status == "wilaya_ok"
    client.post("/logout")
    login(client, DG)
    client.post(f"/nesda/sessions/{s.id}", data={"action": "validate"})
    db.session.refresh(s)
    assert s.nesda_status == "validated"


def test_kpi_status_rules():
    from app.services.kpi import kpi_status, overall_status
    from app.services.period import Period
    past = Period("2024-2025", "A")
    assert kpi_status("groups", 10, 8, past) == "met"
    assert kpi_status("groups", 5, 8, past) == "missed"
    assert kpi_status("dropout_rate", 8, 10, past) == "met", "lower is better"
    assert kpi_status("dropout_rate", 14, 10, past) == "missed"
    assert overall_status(["met", "met", "met", "met", "missed"], past) == "met"
    assert overall_status(["met", "missed", "missed"], past) == "missed"
    assert kpi_status("groups", 3, 8, past) != "none" and kpi_status("groups", 3, None, past) == "none"


def test_demo_seed_and_dashboards(app, client):
    from app.demo import seed_demo
    msg = seed_demo()
    assert "sessions" in msg
    for email in ("mfep@cdegest.dz", "coord.bba@cdegest.dz", "resp.insfp-bba01@cdegest.dz", TEACH, NESDA_W, DG):
        client.post("/logout")
        login(client, email)
        assert client.get("/tableau-de-bord?lang=fr").status_code == 200
        assert client.get("/tableau-de-bord?lang=fr&p=A").status_code == 200
    client.post("/logout")
    login(client, "mfep@cdegest.dz")
    html = client.get("/tableau-de-bord?lang=fr&p=A").get_data(as_text=True)
    # aggregates only: no participant phone number appears on the national view
    assert "05" not in "".join(l for l in html.splitlines() if "dir=\"ltr\"" in l and "tel" in l)
    r = client.get("/comparaison?lang=fr&w=34&w=19&w=16")
    assert r.status_code == 200 and r.get_data(as_text=True).count('class="wcol"') == 3
    assert client.get("/api/public/sessions.json").get_json()["sessions"]


def test_report_flow(app, client):
    from app.demo import seed_demo
    from app.services.period import training_year
    seed_demo()
    y = training_year()[0]
    login(client, RESP)
    r = client.post("/rapports/", data={"y": y, "p": "S1", "action": "transmit"})
    assert r.status_code == 302
    client.post("/logout")
    login(client, "coord.bba@cdegest.dz")
    # coordinator consolidates but cannot transmit to the MFEP
    assert client.post("/rapports/", data={"y": y, "p": "S1", "action": "transmit"}).status_code == 403
    assert client.post("/rapports/", data={"y": y, "p": "S1", "action": "generate"}).status_code == 302
    client.post("/logout")
    login(client, "dfep.bba@cdegest.dz")
    assert client.post("/rapports/", data={"y": y, "p": "S1", "action": "transmit"}).status_code == 302
    client.post("/logout")
    login(client, "mfep@cdegest.dz")
    from app.models import Report
    r = Report.query.filter_by(level="wilaya", year=y, semester=1).first()
    assert r and r.status == "transmitted"
    assert client.get(f"/rapports/{r.id}").status_code == 200
    assert client.get(f"/rapports/{r.id}.xlsx").status_code == 200


def test_teacher_absence_cancels_slot(app, client, tpl):
    s = _session_with_today_slot(client, tpl)
    slot = Slot.query.first()
    r = client.post(f"/sessions/{s.id}/creneaux", data={"action": "cancel", "id": slot.id})
    assert r.status_code == 302 and slot.cancelled and slot.cancel_reason == "enseignant_absent"
    from app.services.training import past_slots
    assert past_slots(slot.group) == [], "a cancelled slot never counts in trainee attendance"
    client.post("/logout")
    login(client, TEACH)
    assert client.post(f"/appel/{slot.id}", data={}).status_code == 403, "no roll call on a cancelled slot"

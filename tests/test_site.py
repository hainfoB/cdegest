"""Site public : pages d'information, événements, signalements et leur gestion par périmètre."""
from datetime import date, timedelta

from app.extensions import db
from app.models import Event, Institute, Ticket
from tests.conftest import login

PAGES = ["/", "/le-cde", "/comment-s-inscrire", "/la-formation", "/faq", "/evenements", "/signaler"]


def test_public_pages_in_three_languages(client):
    for lang in ("fr", "ar", "en"):
        for p in PAGES:
            r = client.get(f"{p}?lang={lang}")
            assert r.status_code == 200, (p, lang)
            html = r.get_data(as_text=True)
            assert 'href="#"' not in html and "/signaler" in html and "/faq" in html


def test_event_lifecycle_and_scope(app, client):
    login(client, "resp.insfp-bba01@cdegest.dz")
    start = (date.today() + timedelta(days=5)).isoformat()
    r = client.post("/gestion/evenements", data={"kind": "portes_ouvertes", "title_fr": "Portes ouvertes BBA",
                                                 "title_ar": "أبواب مفتوحة", "starts_on": start})
    assert r.status_code == 302
    e = Event.query.one()
    assert e.institute.code == "INSFP-BBA-01" and not e.published
    assert client.get(f"/evenements/{e.id}").status_code == 404        # draft not public
    client.post(f"/gestion/evenements/{e.id}/publier")
    assert "Portes ouvertes BBA" in client.get("/evenements?lang=fr").get_data(as_text=True)
    assert "Portes ouvertes BBA" in client.get("/?public=1&lang=fr").get_data(as_text=True)
    # another CDE manager cannot touch it
    client.post("/logout")
    login(client, "resp.insfp-bba02@cdegest.dz")
    assert client.post(f"/gestion/evenements/{e.id}/supprimer").status_code == 404
    # the teacher has no access to event management
    client.post("/logout")
    login(client, "formateur.bba01@cdegest.dz")
    assert client.get("/gestion/evenements").status_code == 403


def test_ticket_flow(app, client):
    inst = Institute.query.filter_by(code="INSFP-BBA-01").one()
    r = client.post("/signaler", data={"category": "inscription", "name": "Test", "phone": "0550123456",
                                       "subject": "Erreur", "message": "Mauvais numéro", "institute": inst.id,
                                       "consent": "1"})
    assert r.status_code == 302
    tk = Ticket.query.one()
    assert tk.wilaya_id == inst.wilaya_id and tk.status == "open"
    assert tk.ref in client.get(r.headers["Location"]).get_data(as_text=True)
    # lookup by reference + phone
    r = client.post("/signalement", data={"ref": tk.ref, "contact": "0550123456"})
    assert r.headers["Location"].endswith(tk.token)
    # honeypot and missing consent are refused
    assert client.post("/signaler", data={"website": "x"}).status_code == 400
    client.post("/signaler", data={"category": "autre", "name": "X", "phone": "1", "subject": "s", "message": "m"})
    assert Ticket.query.count() == 1
    # CDE manager answers; the requester sees the reply
    login(client, "resp.insfp-bba01@cdegest.dz")
    client.post(f"/gestion/signalements/{tk.id}", data={"status": "resolved", "reply": "Corrigé"})
    db.session.refresh(tk)
    assert tk.status == "resolved" and tk.handled_by.email == "resp.insfp-bba01@cdegest.dz"
    assert "Corrigé" in client.get(f"/signalement/{tk.token}").get_data(as_text=True)
    # out-of-scope handlers do not see it
    client.post("/logout")
    login(client, "dfep.setif@cdegest.dz")
    assert client.get(f"/gestion/signalements/{tk.id}").status_code == 404
    client.post("/logout")
    login(client, "nesda.bba@cdegest.dz")       # NESDA only sees attendance/certificate requests
    assert client.get(f"/gestion/signalements/{tk.id}").status_code == 404

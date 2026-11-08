"""Mode réel des connecteurs, testé par le réseau contre le simulateur d'administrations (vrai serveur HTTP local)."""
import json
import threading

import pytest
from werkzeug.serving import make_server

from app.extensions import db
from app.models import ApiCall, AuditLog, Candidature
from app.services import connectors as C
from app.services import real as R
from tests.conftest import login

KEY = "cle-de-recette"


@pytest.fixture(scope="module")
def sim():
    import os
    os.environ.update({"SIM_API_KEY": KEY, "SIM_LATENCY_MS": "0-5", "SIM_ERROR_RATE": "0", "SIM_SLOW_S": "3"})
    from simulateur.app import app as sim_app, STATE
    srv = make_server("127.0.0.1", 0, sim_app, threaded=True)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield {"url": f"http://127.0.0.1:{srv.server_port}", "state": STATE}
    srv.shutdown()


@pytest.fixture()
def wired(app, sim, monkeypatch):
    monkeypatch.setenv("CONN_API_KEY", KEY)
    for code in R.INBOUND:
        c = R.connector(code)
        c.url, c.mode, c.environment, c.timeout_s = sim["url"], "reel", "recette", 2
    db.session.commit()
    for s in sim["state"]["panne"]:
        sim["state"]["panne"][s] = False
    return sim


def test_identity_comes_over_the_network_and_is_translated(wired):
    st, data, src = C.identity("177700000000000555")
    assert st == "trouve"
    assert src == "recette", "test bench data never counts as verified"
    # même personne qu'en mode simulé : le simulateur renvoie son propre format, la correspondance le traduit
    C.set_mode("etat_civil", "simule", None)
    _st, sim_data, _src = C.identity("177700000000000555")
    assert data == sim_data
    call = ApiCall.query.filter_by(connector="etat_civil", mode="reel").first()
    assert call.result == "trouve" and "HTTP 200" in call.fields and "177700" not in call.fields


def test_production_environment_gives_verified(wired):
    R.connector("etat_civil").environment = "production"
    assert C.identity("177700000000000555")[2] == "etat_civil"
    R.connector("mfep_diplomes").environment = "production"
    st, dip, src = C.diplomas("177700000000000555")
    assert st == "trouve" and src == "mfep" and dip[0]["etablissement"] == "INSFP-BBA-01" and isinstance(dip[0]["annee"], int)


def test_level_and_internship_lists(wired):
    st, lev, src = C.level("177700000000000555")
    assert st == "trouve" and lev["libelle"] and isinstance(lev["annee"], int) and src == "recette"
    st, rows = C.stage_list("INSFP-BBA-01")
    assert st == "trouve" and rows and len(rows[0]["nin"]) == 18


def test_unknown_unavailable_and_wrong_key(wired, monkeypatch):
    assert C.identity("177700000000000000")[0] == "inconnu"
    assert C.identity("177700000000009999")[:3:2] == ("indisponible", "declaratif")
    monkeypatch.setenv("CONN_API_KEY", "mauvaise-cle")
    assert C.identity("177700000000000555")[0] == "refuse"
    assert "accès refusé" in R.connector("etat_civil").last_error


def test_transient_error_succeeds_on_retry(wired):
    st, data, _ = C.identity("177700000000007777")
    assert st == "trouve"
    call = ApiCall.query.filter_by(connector="etat_civil", mode="reel").order_by(ApiCall.id.desc()).first()
    assert "2 essais" in call.fields


def test_slow_answer_times_out_within_budget(wired):
    import time
    R.connector("etat_civil").timeout_s = 1
    t0 = time.monotonic()
    st, _, src = C.identity("177700000000008888")
    assert st == "indisponible" and src == "declaratif"
    assert time.monotonic() - t0 < R.BUDGET_S + 2
    assert "délai dépassé" in R.connector("etat_civil").last_error


def test_circuit_breaker_opens_after_five_failures_then_recovers(wired):
    wired["state"]["panne"]["etat_civil"] = True
    for _ in range(R.CIRCUIT_FAILS):
        assert C.identity("177700000000000555")[0] == "indisponible"
    c = R.connector("etat_civil")
    assert R.circuit_open(c)
    assert AuditLog.query.filter_by(action="connector.circuit_open").count() == 1
    wired["state"]["panne"]["etat_civil"] = False
    st, _, _ = C.identity("177700000000000555")
    assert st == "indisponible", "while open, the administration is not queried"
    assert "coupe-circuit" in ApiCall.query.order_by(ApiCall.id.desc()).first().fields
    R.rearm("etat_civil")
    assert C.identity("177700000000000555")[0] == "trouve"
    assert R.connector("etat_civil").fail_count == 0


def test_unexpected_format_is_caught_by_the_mapping(wired):
    m = R.mapping("etat_civil")
    m["fields"]["nom_lat"] = "nom.inexistant"
    R.connector("etat_civil").mapping = json.dumps(m)
    st, _, src = C.identity("177700000000000555")
    assert st == "indisponible" and src == "declaratif"
    assert "format inattendu" in R.connector("etat_civil").last_error


def test_mapping_validation():
    ok, err = R.validate_mapping("etat_civil", json.dumps(R.DEFAULT_MAPPING["etat_civil"]))
    assert ok and err is None
    assert R.validate_mapping("etat_civil", "{")[1].startswith("JSON invalide")
    bad = dict(R.DEFAULT_MAPPING["etat_civil"], fields={"nom_lat": "nom.latin"})
    assert "obligatoires" in R.validate_mapping("etat_civil", json.dumps(bad))[1]
    bad = dict(R.DEFAULT_MAPPING["men"], fields={"libelle": "niveau|inconnue"})
    assert "conversion inconnue" in R.validate_mapping("men", json.dumps(bad))[1]


def test_settings_screen(app, client, wired):
    login(client, "admin@cdegest.dz")
    r = client.get("/connecteurs")
    assert r.status_code == 200 and 'value="health"' in r.get_data(as_text=True)
    client.post("/connecteurs", data={"action": "health", "code": "etat_civil"})
    assert "HTTP 200" in AuditLog.query.filter_by(action="connector.health").one().details
    # production refusée sans confirmation de convention
    client.post("/connecteurs", data={"action": "config", "code": "men", "url": wired["url"], "environment": "production", "timeout": "4"})
    assert R.connector("men").environment == "recette"
    client.post("/connecteurs", data={"action": "config", "code": "men", "url": wired["url"], "environment": "production",
                                      "timeout": "4", "convention": "1"})
    assert R.connector("men").environment == "production" and R.connector("men").timeout_s == 4
    assert AuditLog.query.filter_by(action="connector.config", target="men").count() == 1
    # adresse vide : impossible de repasser en mode réel
    client.post("/connecteurs", data={"action": "config", "code": "mfep_stage", "url": "", "environment": "recette"})
    client.post("/connecteurs", data={"action": "mode", "code": "mfep_stage", "mode": "simule"})
    client.post("/connecteurs", data={"action": "mode", "code": "mfep_stage", "mode": "reel"})
    assert C.mode("mfep_stage") == "simule"


def test_test_bench_identity_does_not_count_as_verified(app, wired):
    from app.services import kpi as K
    from app.models import Institute
    inst = Institute.query.first()
    st, data, src = C.identity("177700000000000555")
    c = Candidature(institute_id=inst.id, last_name="X", first_name="Y", phone="0550", status="nouvelle", identity_source=src)
    db.session.add(c)
    db.session.commit()
    assert c.identity_source == "recette" and c.identity_source != "etat_civil"

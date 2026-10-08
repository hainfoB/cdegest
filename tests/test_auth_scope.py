import pytest

from app.models import User
from app.security import visible_institutes, visible_users, visible_wilayas
from tests.conftest import login

ACCOUNTS = ["mfep@cdegest.dz", "dfep.bba@cdegest.dz", "coord.bba@cdegest.dz",
            "resp.insfp-bba01@cdegest.dz", "formateur.bba01@cdegest.dz"]


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_public_home_in_three_languages(client):
    assert "مراكز تطوير المقاولاتية" in client.get("/?lang=ar").get_data(as_text=True)
    assert "Centres de développement" in client.get("/?lang=fr").get_data(as_text=True)
    assert "Entrepreneurship Development" in client.get("/?lang=en").get_data(as_text=True)


def test_rtl_only_for_arabic(client):
    assert 'dir="rtl"' in client.get("/?lang=ar").get_data(as_text=True)
    assert 'dir="ltr"' in client.get("/?lang=fr").get_data(as_text=True)


def test_dashboard_requires_login(client):
    r = client.get("/tableau-de-bord")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_bad_password(client):
    r = login(client, "mfep@cdegest.dz", "wrong")
    assert r.status_code == 200
    assert "/tableau-de-bord" not in r.headers.get("Location", "")


@pytest.mark.parametrize("email", ACCOUNTS)
def test_each_demo_account_reaches_its_dashboard(client, email):
    assert login(client, email).status_code == 302
    r = client.get("/tableau-de-bord?lang=fr")
    assert r.status_code == 200


def test_open_redirect_blocked(client):
    r = client.post("/login?next=https://evil.example", data={"email": "mfep@cdegest.dz", "password": "Cde@2026"})
    assert r.headers["Location"].endswith("/tableau-de-bord")


def test_inactive_account_refused(app, client):
    from app.extensions import db
    u = User.query.filter_by(email="coord.bba@cdegest.dz").first()
    u.active = False
    db.session.commit()
    assert login(client, "coord.bba@cdegest.dz").status_code == 200


# ---------- perimeters (the critical part) ----------

def _u(email):
    return User.query.filter_by(email=email).first()


def test_mfep_sees_all_wilayas_but_no_institute_staff(app):
    u = _u("mfep@cdegest.dz")
    assert visible_wilayas(u).count() == 69
    roles = {x.role for x in visible_users(u)}
    assert roles <= {"mfep", "dfep", "coord"}, "MFEP must not list institute staff"


@pytest.mark.parametrize("email", ["dfep.bba@cdegest.dz", "coord.bba@cdegest.dz"])
def test_wilaya_roles_limited_to_bba(app, email):
    u = _u(email)
    codes = {i.code for i in visible_institutes(u)}
    assert codes == {"INSFP-BBA-01", "INSFP-BBA-02"}
    assert [w.code for w in visible_wilayas(u)] == ["34"]
    assert all(x.scope_wilaya and x.scope_wilaya.code == "34" for x in visible_users(u))


def test_dfep_and_coord_have_same_perimeter(app):
    a, b = _u("dfep.bba@cdegest.dz"), _u("coord.bba@cdegest.dz")
    assert {i.id for i in visible_institutes(a)} == {i.id for i in visible_institutes(b)}
    assert {x.id for x in visible_users(a)} == {x.id for x in visible_users(b)}


def test_resp_limited_to_own_institute(app):
    u = _u("resp.insfp-bba01@cdegest.dz")
    assert [i.code for i in visible_institutes(u)] == ["INSFP-BBA-01"]
    assert all(x.institute and x.institute.code == "INSFP-BBA-01" for x in visible_users(u))


def test_teacher_sees_only_himself(app):
    u = _u("formateur.bba01@cdegest.dz")
    assert [x.email for x in visible_users(u)] == [u.email]


def test_wilaya_dashboard_does_not_leak_other_wilayas(client):
    login(client, "coord.bba@cdegest.dz")
    html = client.get("/tableau-de-bord?lang=fr").get_data(as_text=True)
    assert "INSFP-BBA-01" in html and "INSFP-STF-01" not in html and "INSFP-MSL-01" not in html


def test_compare_reserved_to_national(client):
    login(client, "coord.bba@cdegest.dz")
    assert client.get("/comparaison?w=34&w=19").status_code == 403


def test_compare_caps_at_five(client):
    login(client, "mfep@cdegest.dz")
    html = client.get("/comparaison?lang=fr&w=01&w=16&w=19&w=31&w=34&w=69").get_data(as_text=True)
    assert html.count('class="wcol"') == 5


def test_training_year():
    from datetime import date
    from app.services.period import training_year
    assert training_year(date(2026, 10, 8))[0] == "2026-2027" and training_year(date(2026, 10, 8))[3] == 1
    assert training_year(date(2027, 3, 1))[3] == 3 and training_year(date(2027, 8, 31))[0] == "2026-2027"

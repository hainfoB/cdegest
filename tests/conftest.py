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


def login(client, email, password=PWD):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)

"""Command line: `flask --app wsgi seed-base` (idempotent, safe to run at every deploy)."""
import os
import secrets
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
    ("INSFP-BBA-03", "34", "INSFP Ras El Oued", "المعهد الوطني المتخصص في التكوين المهني رأس الوادي"),
    ("INSFP-STF-01", "19", "INSFP Sétif 01", "المعهد الوطني المتخصص في التكوين المهني سطيف 01"),
    ("INSFP-STF-02", "19", "INSFP Sétif 02", "المعهد الوطني المتخصص في التكوين المهني سطيف 02"),
    ("INSFP-MSL-01", "28", "INSFP M'Sila 01", "المعهد الوطني المتخصص في التكوين المهني المسيلة 01"),
]

# show = affiché sur la page de connexion de démonstration ; NIN fictifs (18 chiffres)
# roles = habilitations (rôle, périmètre) ; plusieurs rôles pour une même personne (RG-34)
DEMO_USERS = [
    {"nin": "109900000000000011", "email": "admin@cdegest.dz", "pwd_env": "ADMIN_PASSWORD", "name": "Administrateur plateforme",
     "roles": [("admin", None)], "show": False},
    {"nin": "109900000000001012", "email": "mfep@cdegest.dz", "pwd_env": "PASSWORD_MFEP", "name": "Direction centrale MFEP",
     "roles": [("mfep", None)], "show": True},
    {"nin": "109934000000002013", "email": "dfep.bba@cdegest.dz", "pwd_env": "PASSWORD_DFEP_BBA", "name": "DFEP Bordj Bou Arréridj",
     "roles": [("dfep", "w:34")], "show": True},
    {"nin": "109934000000003014", "email": "coord.bba@cdegest.dz", "pwd_env": "PASSWORD_COORD_BBA", "name": "Coordinateur CDE BBA",
     "roles": [("coord", "w:34"), ("formateur", "i:INSFP-BBA-02")], "show": True},
    {"nin": "109934010000004015", "email": "resp.insfp-bba01@cdegest.dz", "pwd_env": "PASSWORD_RESP_BBA01", "name": "Responsable CDE INSFP BBA 01",
     "roles": [("resp", "i:INSFP-BBA-01"), ("formateur", "i:INSFP-BBA-01")], "show": True},
    {"nin": "109934010000005016", "email": "formateur.bba01@cdegest.dz", "pwd_env": "PASSWORD_ENSEIGNANT_BBA01", "name": "Enseignant INSFP BBA 01",
     "roles": [("formateur", "i:INSFP-BBA-01"), ("formateur", "i:INSFP-BBA-02")], "show": True},
    {"nin": "109934000000006017", "email": "nesda.bba@cdegest.dz", "pwd_env": "PASSWORD_NESDA_BBA", "name": "Représentant NESDA BBA",
     "roles": [("nesda", "w:34")], "show": True},
    {"nin": "109900000000007018", "email": "dg.nesda@cdegest.dz", "pwd_env": "PASSWORD_DG_NESDA", "name": "Direction générale NESDA",
     "roles": [("nesda_dg", None)], "show": True},
    {"nin": "100234000000012024", "email": "candidat.demo@cdegest.dz", "pwd_env": "PASSWORD_CANDIDAT_DEMO", "name": "Lina Saidi",
     "roles": [("candidat", None)], "show": True, "phone": "0550123456", "mobile": "whatsapp", "lang": "fr"},
    {"nin": "109934020000008019", "email": "resp.insfp-bba02@cdegest.dz", "name": "Responsable CDE INSFP BBA 02",
     "roles": [("resp", "i:INSFP-BBA-02")], "show": False},
    {"nin": "109919000000009021", "email": "dfep.setif@cdegest.dz", "name": "DFEP Sétif", "roles": [("dfep", "w:19")], "show": False},
    {"nin": "109919000000010022", "email": "coord.setif@cdegest.dz", "name": "Coordinateur CDE Sétif", "roles": [("coord", "w:19")], "show": False},
    {"nin": "109928000000011023", "email": "dfep.msila@cdegest.dz", "name": "DFEP M'Sila", "roles": [("dfep", "w:28")], "show": False},
]
BY_EMAIL = {u["email"]: u for u in DEMO_USERS}


def seed_base(demo=True, default_password=None):
    """Mots de passe : variable d'environnement de chaque compte, sinon `default_password` (tests),
    sinon un secret aléatoire inconnu (à réinitialiser avec `flask set-password`)."""
    from .models import Habilitation
    from .utils import utcnow
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
        if User.by_nin(spec["nin"]):
            continue
        u = User(email=spec["email"], name=spec["name"], lang=spec.get("lang", "ar"), identity_source="simule", charter_at=utcnow(),
                 phone=spec.get("phone"), mobile_channel=spec.get("mobile", "sms"), email_verified_at=utcnow())
        if spec.get("mobile") == "whatsapp":
            u.wa_consent_at = utcnow()
        u.nin = spec["nin"]
        pwd = os.environ.get(spec.get("pwd_env", "")) or default_password or secrets.token_urlsafe(24)
        u.set_password(pwd)
        db.session.add(u)
        db.session.flush()
        for role, scope in spec["roles"]:
            inst = insts.get(scope[2:]) if scope and scope.startswith("i:") else None
            wil = by_code.get(scope[2:]) if scope and scope.startswith("w:") else None
            db.session.add(Habilitation(user=u, role=role, institute=inst, wilaya=wil or (inst.wilaya if inst else None),
                                        reason="compte de démonstration" if demo else "installation"))
        created += 1
    db.session.commit()
    return created


def register_cli(app):
    @app.cli.command("seed-base")
    def seed_base_cmd():
        """Wilayas, institutes and (in demo mode) demo accounts. Idempotent."""
        n = seed_base(demo=app.config["DEMO_MODE"])
        click.echo(f"seed-base: {n} élément(s) créé(s)")

    @app.cli.command("seed-demo")
    def seed_demo_cmd():
        """Fictitious demonstration data (sessions, attendance, objectives, reports). Runs once."""
        if not app.config["DEMO_MODE"]:
            click.echo("seed-demo: DEMO_MODE=0, rien à faire")
            return
        from .demo import seed_demo, seed_site
        click.echo(seed_demo())
        click.echo(seed_site())

    @app.cli.command("init-local")
    def init_local_cmd():
        """Create .env with a secret key and one private password per account (local use)."""
        from pathlib import Path
        env = Path(app.root_path).parent / ".env"
        if env.exists():
            click.echo(".env existe déjà : rien à faire")
            return
        words = ["Atlas", "Sahara", "Tassili", "Hoggar", "Djurdjura", "Babor", "Aures", "Medjerda"]
        lines = ["FLASK_APP=wsgi", "DEMO_MODE=1", "SHOW_DEMO_ACCOUNTS=0", f"SECRET_KEY={secrets.token_hex(32)}"]
        table = []
        for spec in DEMO_USERS:
            if "pwd_env" not in spec:
                continue
            pwd = f"{secrets.choice(words)}-{secrets.randbelow(9000) + 1000}-{secrets.token_urlsafe(4)}"
            lines.append(f"{spec['pwd_env']}={pwd}")
            table.append(f"{spec['name']:<34} NIN {spec['nin']:<20} {pwd}")
        env.write_text("\n".join(lines) + "\n", encoding="utf-8")
        acces = Path(app.root_path).parent / "ACCES_LOCAL.txt"
        acces.write_text("CDEgest — accès locaux (fichier privé, ne pas partager)\nhttp://localhost:5000/login\n\n" + "\n".join(table) + "\n", encoding="utf-8")
        click.echo("Accès créés et enregistrés dans ACCES_LOCAL.txt :")
        click.echo("\n".join(table))

    @app.cli.command("set-password")
    @click.argument("nin")
    @click.password_option()
    def set_password_cmd(nin, password):
        """Change le mot de passe d'un compte, désigné par son NIN (saisi, jamais affiché)."""
        u = User.by_nin(nin)
        if not u:
            raise click.ClickException("compte introuvable")
        u.set_password(password)
        db.session.commit()
        click.echo("mot de passe modifié")

    @app.cli.command("notify-run")
    def notify_run_cmd():
        """Envoie les messages programmés, puis les rappels (M-05, M-09, M-11, M-13, M-15). À lancer toutes les heures."""
        from .services import events as E
        from .services.notify import deliver_due
        n = deliver_due() + E.run_reminders()
        db.session.commit()
        click.echo(f"notify-run: {n} message(s)")

    @app.cli.command("notify-digest")
    def notify_digest_cmd():
        """Résumés quotidiens des agents (M-14, M-16). À lancer à 8 h les jours ouvrables."""
        from .services import events as E
        n = E.run_digests()
        db.session.commit()
        click.echo(f"notify-digest: {n} message(s)")

    @app.cli.command("reset-demo")
    @click.option("--if-version", default=None, help="Réinitialise seulement si la version de démo enregistrée est différente.")
    def reset_demo_cmd(if_version):
        """Recrée la base de démonstration (données fictives). Refusé si DEMO_MODE=0."""
        from .models import AppMeta
        if not app.config["DEMO_MODE"]:
            click.echo("reset-demo: DEMO_MODE=0, refusé")
            return
        try:
            cur = db.session.get(AppMeta, "demo_version")
        except Exception:
            db.session.rollback()
            cur = None
        if if_version and cur is not None and cur.value == if_version:
            click.echo(f"reset-demo: version {if_version} déjà en place")
            return
        db.drop_all()
        db.session.execute(db.text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()
        db.create_all()
        from flask_migrate import stamp
        stamp()
        seed_base(demo=True)
        from .demo import seed_demo, seed_site
        click.echo(seed_demo())
        click.echo(seed_site())
        db.session.merge(AppMeta(key="demo_version", value=if_version or "manual"))
        db.session.commit()
        click.echo("reset-demo: base recréée")

    @app.cli.command("connectors-env")
    def connectors_env_cmd():
        """Adresse par défaut des connecteurs entrants depuis CONN_BASE_URL / CONN_URL_<CODE> (si vide)."""
        from .services import real
        n = real.configure_from_env()
        db.session.commit()
        click.echo(f"connectors-env: {n} adresse(s) renseignée(s)")

    @app.cli.command("sync-passwords")
    def sync_passwords_cmd():
        """Re-apply the PASSWORD_* environment variables to existing accounts."""
        n = 0
        for spec in DEMO_USERS:
            pwd = os.environ.get(spec.get("pwd_env", ""))
            u = User.by_nin(spec["nin"])
            if pwd and u and not u.check_password(pwd):
                u.set_password(pwd)
                n += 1
        db.session.commit()
        click.echo(f"sync-passwords: {n} compte(s) mis à jour")

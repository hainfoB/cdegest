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
    @click.option("--url", default="http://localhost:5000", help="Adresse de l'application (serveur : https://…).")
    @click.option("--sim-url", default="http://127.0.0.1:5099", help="Adresse du simulateur d'administrations (vide = aucun).")
    def init_local_cmd(url, sim_url):
        """Crée ou complète .env (clés, un mot de passe privé par compte, simulateur) et écrit ACCES_LOCAL.txt.

        Un .env existant est conservé : seules les valeurs manquantes sont ajoutées (mise à jour d'une ancienne version).
        """
        from pathlib import Path
        root = Path(app.root_path).parent
        env = root / ".env"
        cur = {}
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, _, v = line.partition("=")
                    cur[k.strip()] = v.strip()
        words = ["Atlas", "Sahara", "Tassili", "Hoggar", "Djurdjura", "Babor", "Aures", "Medjerda"]
        sim_key = cur.get("SIM_API_KEY") or secrets.token_urlsafe(18)
        wanted = {"FLASK_APP": "wsgi", "DEMO_MODE": "1", "SHOW_DEMO_ACCOUNTS": "0", "SHOW_SIMULATED_MESSAGES": "1",
                  "TZ": "Africa/Algiers", "APP_URL": url, "SECRET_KEY": secrets.token_hex(32), "NIN_KEY": secrets.token_hex(32)}
        if sim_url:
            wanted.update({"CONN_BASE_URL": sim_url, "CONN_API_KEY": sim_key, "SIM_API_KEY": sim_key})
        for spec in DEMO_USERS:
            if "pwd_env" in spec:
                wanted[spec["pwd_env"]] = f"{secrets.choice(words)}-{secrets.randbelow(9000) + 1000}-{secrets.token_urlsafe(4)}"
        added = [k for k in wanted if k not in cur]
        if added:
            with env.open("a", encoding="utf-8") as f:
                if cur:
                    f.write("\n# ajouté par init-local (mise à jour)\n")
                for k in added:
                    f.write(f"{k}={wanted[k]}\n")
                    cur[k] = wanted[k]
        table = [f"  {spec['name']:<34} NIN {spec['nin']:<20} {cur[spec['pwd_env']]}"
                 for spec in DEMO_USERS if "pwd_env" in spec]
        text = ["CDEgest v1.3 — accès (fichier privé, ne pas partager). Données fictives.", "",
                f"Adresse : {cur.get('APP_URL', url)}/login", "",
                "Connexion : NIN (18 chiffres) + mot de passe, puis code à 6 chiffres. En démonstration, aucun message",
                "n'est envoyé : le message simulé (avec le code) s'affiche sous le champ « Code reçu ».", "", "COMPTES"] + table
        if cur.get("CONN_BASE_URL"):
            text += ["", "ÉCHANGES AVEC L'ÉTAT : mode réel en recette, vers le simulateur d'administrations",
                     f"  ({cur['CONN_BASE_URL']}). Menu « Échanges avec l'État » (administrateur ou MFEP).",
                     "  NIN de test (fin du numéro) : 0000 inconnu · 9999 indisponible · 8888 trop lent · 7777 erreur passagère",
                     "  (réussit au 2e essai) · autre : identité fictive trouvée (ex. 177700000000000555)."]
        (root / "ACCES_LOCAL.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
        click.echo(f"init-local: .env {'complété' if added and len(added) < len(wanted) else 'créé' if added else 'déjà complet'}"
                   f" ({len(added)} valeur(s) ajoutée(s)) ; accès dans ACCES_LOCAL.txt")

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

    @app.cli.command("backup")
    @click.option("--dest", default=None, help="Dossier des sauvegardes (défaut : ../sauvegardes-cdegest).")
    @click.option("--keep", default=14, help="Nombre de sauvegardes conservées.")
    def backup_cmd(dest, keep):
        """Sauvegarde à chaud de la base SQLite (à programmer chaque nuit). PostgreSQL : utiliser pg_dump ou l'hébergeur."""
        import sqlite3
        from datetime import datetime
        from pathlib import Path
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        if not uri.startswith("sqlite:///"):
            raise click.ClickException("base non SQLite : utilisez pg_dump ou la sauvegarde de l'hébergeur")
        src = db.engine.url.database
        folder = Path(dest or Path(app.root_path).parent.parent / "sauvegardes-cdegest")
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"cdegest-{datetime.now():%Y%m%d-%H%M}.db"
        with sqlite3.connect(src) as a, sqlite3.connect(out) as b:
            a.backup(b)
        olds = sorted(folder.glob("cdegest-*.db"))[:-keep]
        for o in olds:
            o.unlink()
        click.echo(f"backup: {out} ({out.stat().st_size // 1024} Ko), {len(olds)} ancienne(s) supprimée(s)")

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
        db.session.expunge_all()            # oublie les objets lus avant la suppression (ex. version de démo)
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
        from .services import connectors as C
        for code in real.INBOUND:
            c = real.connector(code)
            if c.url:
                ok, msg = real.health(code)
                click.echo(f"connectors-env: {code} [{C.mode(code)}, {c.environment}] → {'raccordé' if ok else 'ÉCHEC'} ({msg})")

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

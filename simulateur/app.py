"""Simulateur d'administrations pour CDEgest (recette du mode « réel »).

Service HTTP indépendant de CDEgest : il joue le rôle de l'état civil, du SI du MFEP (diplômes, stage pratique)
et de l'Éducation nationale, avec un format de réponse qui leur est propre (différent de celui de CDEgest),
des temps de réponse variables et des pannes. Aucune donnée réelle : tout est fabriqué à partir du NIN.

NIN de test (fin du numéro) :
  0000 → personne inconnue (404)          9999 → service indisponible (503)
  8888 → réponse trop lente (délai dépassé) 7777 → erreur passagère : 1er appel en échec (500), le suivant réussit
Variables : SIM_API_KEY (clé exigée dans l'en-tête X-Api-Key), SIM_LATENCY_MS (ex. 80-600),
SIM_ERROR_RATE (part d'erreurs 503 aléatoires, ex. 0.03), SIM_SLOW_S (durée de la réponse lente, 8 s).
"""
import hashlib
import hmac
import os
import random
import threading
import time
from datetime import date, timedelta

from flask import Flask, jsonify, request

app = Flask(__name__)
app.json.ensure_ascii = False

SERVICES = ("etat_civil", "mfep", "men")
STATE = {"panne": {s: False for s in SERVICES}, "flaky": {}, "appels": {s: 0 for s in SERVICES}}
LOCK = threading.Lock()

LAST_M = ["Benali", "Saidi", "Bouzid", "Khelifi", "Mansouri", "Hamdi", "Boudiaf", "Cherif", "Ziani", "Amrani", "Belkacem", "Mebarki"]
LAST_A = ["بن علي", "سعيدي", "بوزيد", "خليفي", "منصوري", "حمدي", "بوضياف", "شريف", "زياني", "عمراني", "بلقاسم", "مباركي"]
FIRST_M = [("Yacine", "ياسين"), ("Amine", "أمين"), ("Karim", "كريم"), ("Walid", "وليد"), ("Sofiane", "سفيان"), ("Nabil", "نبيل")]
FIRST_F = [("Lina", "لينا"), ("Amel", "أمال"), ("Sarah", "سارة"), ("Imane", "إيمان"), ("Meriem", "مريم"), ("Nour", "نور")]
COMMUNES = [("3401", "Bordj Bou Arréridj", "برج بوعريريج"), ("3402", "Ras El Oued", "رأس الوادي"),
            ("1901", "Sétif", "سطيف"), ("2801", "M'Sila", "المسيلة"), ("1601", "Alger-Centre", "الجزائر الوسطى")]
DIPLOMAS = [("BTS", "Informatique — bases de données"), ("BTS", "Comptabilité et gestion"), ("CAP", "Menuiserie"),
            ("BT", "Électricité bâtiment"), ("BTS", "Marketing"), ("CMP", "Pâtisserie")]
LEVELS = [("4AM", "4e année moyenne"), ("1AS", "1re année secondaire"), ("2AS", "2e année secondaire"),
          ("3AS", "3e année secondaire"), ("UNIV", "Universitaire")]


def cfg(name, default):
    return os.environ.get(name, default)


def seed(n):
    # même empreinte que le mode simulé de CDEgest : une personne a la même identité dans les deux modes
    return int(hashlib.sha256(("sim|" + n).encode()).hexdigest()[:12], 16)


def err(status, code, message):
    r = jsonify({"erreur": code, "message": message})
    r.status_code = status
    return r


def gate(service, nin=None):
    """Contrôles communs : clé d'accès, panne déclarée, latence, NIN de test. Renvoie une réponse d'erreur ou None."""
    key = cfg("SIM_API_KEY", "")
    if key and not hmac.compare_digest(request.headers.get("X-Api-Key", ""), key):
        return err(401, "ACCES_REFUSE", "Clé d'accès absente ou invalide")
    with LOCK:
        STATE["appels"][service] += 1
    lo, _, hi = cfg("SIM_LATENCY_MS", "80-600").partition("-")
    time.sleep(random.uniform(int(lo), int(hi or lo)) / 1000)
    if STATE["panne"][service]:
        return err(503, "SERVICE_EN_MAINTENANCE", "Service momentanément indisponible")
    if nin is not None:
        if not (nin.isdigit() and len(nin) == 18):
            return err(400, "NIN_INVALIDE", "Le NIN comporte 18 chiffres")
        if nin.endswith("9999"):
            return err(503, "SERVICE_INDISPONIBLE", "Service momentanément indisponible")
        if nin.endswith("8888"):
            time.sleep(float(cfg("SIM_SLOW_S", "8")))
        if nin.endswith("7777"):
            k = f"{service}|{nin}"
            with LOCK:
                n = STATE["flaky"].get(k, 0)
                STATE["flaky"][k] = n + 1
            if n % 2 == 0:
                return err(500, "ERREUR_INTERNE", "Erreur passagère")
        if nin.endswith("0000"):
            return err(404, "PERSONNE_INCONNUE", "Aucun enregistrement pour ce NIN")
    if random.random() < float(cfg("SIM_ERROR_RATE", "0")):
        return err(503, "SERVICE_INDISPONIBLE", "Service momentanément indisponible")
    return None


def person(n):
    s = seed(n)
    female = s % 2 == 0
    fm, fa = (FIRST_F if female else FIRST_M)[(s // 7) % 6]
    k = (s // 11) % len(LAST_M)
    com = COMMUNES[(s // 13) % len(COMMUNES)]
    born = date(1990, 1, 1) + timedelta(days=(s // 17) % (365 * 16))
    return {"identifiant": n, "nom": {"latin": LAST_M[k].upper(), "arabe": LAST_A[k]},
            "prenom": {"latin": fm, "arabe": fa}, "sexe": 2 if female else 1,
            "naissance": {"date": born.strftime("%d/%m/%Y"),
                          "commune": {"code": com[0], "libelle_fr": com[1], "libelle_ar": com[2]}},
            "statut": "VIVANT"}


# ------------------------------------------------------------------ état civil (ministère de l'Intérieur)

@app.get("/api/etat-civil/v1/personnes/<nin>")
def etat_civil(nin):
    return gate("etat_civil", nin) or jsonify(person(nin))


# ------------------------------------------------------------------ SI du MFEP

@app.get("/api/mfep/v1/diplomes")
def mfep_diplomes():
    nin = request.args.get("nin", "")
    e = gate("mfep", nin)
    if e:
        return e
    s = seed(nin)
    d = DIPLOMAS[(s // 19) % len(DIPLOMAS)]
    return jsonify({"nin": nin, "diplomes": [{"type": d[0], "specialite": d[1], "etablissement": {"code": "INSFP-BBA-01"},
                                              "session": 2018 + (s // 23) % 8}]})


@app.get("/api/mfep/v1/etablissements/<code>/stagiaires-en-stage")
def mfep_stage(code):
    e = gate("mfep")
    if e:
        return e
    base = seed(code)
    out = []
    for k in range(int(request.args.get("nombre", 6))):
        n = f"1{(base + k * 7919) % 10**17:017d}"
        if n[-4:] in ("0000", "9999", "8888", "7777"):
            continue
        p = person(n)
        out.append({"nin": n, "nom": p["nom"]["latin"], "prenom": p["prenom"]["latin"],
                    "date_debut": date.today().isoformat(), "date_fin": (date.today() + timedelta(days=90)).isoformat()})
    return jsonify({"etablissement": code, "stagiaires": out})


# ------------------------------------------------------------------ Éducation nationale

@app.get("/api/men/v1/eleves/<nin>/scolarite")
def men(nin):
    e = gate("men", nin)
    if e:
        return e
    s = seed(nin)
    last = (s // 29) % len(LEVELS)
    born = int(person(nin)["naissance"]["date"][-4:])
    y0 = born + 15                     # 4e année moyenne vers 15 ans, puis une année par niveau
    cursus = [{"niveau_code": LEVELS[i][0], "niveau": LEVELS[i][1], "annee_scolaire": f"{y0 + i}-{y0 + i + 1}"}
              for i in range(last + 1)]
    return jsonify({"nin": nin, "cursus": cursus})


# ------------------------------------------------------------------ santé et pilotage de la recette

@app.get("/api/sante")
def sante():
    return jsonify({"statut": "ok", "services": {s: ("panne" if STATE["panne"][s] else "ok") for s in SERVICES},
                    "appels": STATE["appels"], "version": "simulateur-1.0"})


@app.route("/api/_controle", methods=["GET", "POST"])
def controle():
    """Déclarer ou lever une panne d'un service (pour les essais) : {"service": "etat_civil", "panne": true}."""
    key = cfg("SIM_CONTROL_KEY", cfg("SIM_API_KEY", ""))
    if key and not hmac.compare_digest(request.headers.get("X-Api-Key", ""), key):
        return err(401, "ACCES_REFUSE", "Clé d'accès absente ou invalide")
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        if body.get("service") not in SERVICES:
            return err(400, "SERVICE_INCONNU", "service : etat_civil, mfep ou men")
        STATE["panne"][body["service"]] = bool(body.get("panne"))
    return jsonify({"panne": STATE["panne"]})


@app.get("/")
def index():
    return jsonify({"service": "Simulateur d'administrations — recette CDEgest", "donnees": "fictives",
                    "points_d_acces": ["/api/etat-civil/v1/personnes/{nin}", "/api/mfep/v1/diplomes?nin=",
                                       "/api/mfep/v1/etablissements/{code}/stagiaires-en-stage",
                                       "/api/men/v1/eleves/{nin}/scolarite", "/api/sante"]})

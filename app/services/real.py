"""Mode « réel » des connecteurs : appel HTTP au serveur d'une administration (EP-12, CDC technique §6).

Le programme ne dépend pas du format d'une administration : il suit le contrat de CDEgest, et une
correspondance de champs (modifiable à l'écran, au format JSON) traduit la réponse du partenaire.
Le jour où une administration fournit sa documentation, on règle l'adresse et la correspondance, sans
réécrire le programme.

Fiabilité :
- délai d'attente par appel (5 s par défaut) et budget total de 8 s ;
- jusqu'à 3 essais si le serveur ne répond pas ou renvoie une erreur 5xx (pas sur 4xx) ;
- coupe-circuit : après 5 échecs consécutifs, le service est considéré indisponible pendant 5 minutes
  (saisie déclarative, alerte au journal d'audit), puis un nouvel essai est fait ;
- aucun NIN en clair dans les journaux.

Secrets (variables d'environnement, jamais en base) :
  CONN_API_KEY_<CODE> ou CONN_API_KEY      → en-tête X-Api-Key
  CONN_CERT_<CODE>, CONN_KEY_<CODE>        → certificat client (mTLS), chemins de fichiers
  CONN_CA_<CODE>                           → autorité de certification du partenaire
"""
import copy
import json
import os
import time
from datetime import date, timedelta

import requests

from ..extensions import db
from ..models import AuditLog, Connector
from ..utils import utcnow

INBOUND = ("etat_civil", "mfep_diplomes", "mfep_stage", "men")
SOURCE = {"etat_civil": "etat_civil", "mfep_diplomes": "mfep", "mfep_stage": "mfep", "men": "men"}
ENVIRONMENTS = ("recette", "production")
MAX_TRIES = 3
BUDGET_S = 8.0
CIRCUIT_FAILS = 5
CIRCUIT_MINUTES = 5

# Correspondance par défaut : celle du simulateur d'administrations. À adapter à la documentation réelle.
# "path" : chemin appelé ({nin}, {etablissement}) ; "params" : paramètres d'URL ; "list" : liste dans la réponse ;
# "pick" : "last" ou "first" pour ne garder qu'un élément ; "fields" : champ CDEgest → chemin dans la réponse
# (points pour descendre, « | » pour une conversion : date_dmy, date_iso, sexe12, upper_title, str, int).
DEFAULT_MAPPING = {
    "etat_civil": {
        "path": "/api/etat-civil/v1/personnes/{nin}",
        "fields": {"nom_lat": "nom.latin|upper_title", "prenom_lat": "prenom.latin", "nom_ar": "nom.arabe",
                   "prenom_ar": "prenom.arabe", "sexe": "sexe|sexe12", "date_naissance": "naissance.date|date_dmy",
                   "lieu_naissance": "naissance.commune.code|str", "commune_fr": "naissance.commune.libelle_fr",
                   "commune_ar": "naissance.commune.libelle_ar"},
    },
    "mfep_diplomes": {
        "path": "/api/mfep/v1/diplomes", "params": {"nin": "{nin}"}, "list": "diplomes",
        "fields": {"diplome": "type", "specialite": "specialite", "etablissement": "etablissement.code",
                   "annee": "session|int"},
    },
    "mfep_stage": {
        "path": "/api/mfep/v1/etablissements/{etablissement}/stagiaires-en-stage", "list": "stagiaires",
        "fields": {"nin": "nin|str", "nom": "nom|upper_title", "prenom": "prenom", "debut": "date_debut|date_iso",
                   "fin": "date_fin|date_iso"},
    },
    "men": {
        "path": "/api/men/v1/eleves/{nin}/scolarite", "list": "cursus", "pick": "last",
        "fields": {"niveau": "niveau_code", "libelle": "niveau", "annee": "annee_scolaire|first_year"},
    },
}
HEALTH_PATH = "/api/sante"
REQUIRED = {"etat_civil": ("nom_lat", "prenom_lat", "sexe", "date_naissance"), "mfep_diplomes": ("diplome",),
            "mfep_stage": ("nin",), "men": ("libelle",)}


class FormatError(Exception):
    pass


# ------------------------------------------------------------------ réglages

def connector(code):
    c = db.session.get(Connector, code)
    if c is None:
        c = Connector(code=code, mode="simule", environment="recette", timeout_s=5, fail_count=0)
        db.session.add(c)
    return c


def mapping(code):
    c = db.session.get(Connector, code)
    if c is not None and c.mapping:
        try:
            return json.loads(c.mapping)
        except ValueError:
            pass
    return copy.deepcopy(DEFAULT_MAPPING[code])


def validate_mapping(code, text):
    """Contrôle une correspondance saisie à l'écran. Renvoie (dict, erreur)."""
    try:
        m = json.loads(text)
    except ValueError as e:
        return None, f"JSON invalide : {e}"
    if not isinstance(m, dict) or not isinstance(m.get("path"), str) or not m["path"].startswith("/"):
        return None, "« path » doit être un chemin commençant par /"
    if not isinstance(m.get("fields"), dict) or not m["fields"]:
        return None, "« fields » doit lister les champs"
    missing = [f for f in REQUIRED[code] if f not in m["fields"]]
    if missing:
        return None, "champs obligatoires absents : " + ", ".join(missing)
    for k, v in m["fields"].items():
        if not isinstance(v, str) or not v:
            return None, f"chemin vide pour « {k} »"
        conv = v.partition("|")[2]
        if conv and conv not in CONVERSIONS:
            return None, f"conversion inconnue « {conv} » ({', '.join(CONVERSIONS)})"
    return m, None


def secrets(code):
    up = code.upper()
    env = os.environ.get
    key = env(f"CONN_API_KEY_{up}") or env("CONN_API_KEY")
    cert, pkey, ca = env(f"CONN_CERT_{up}"), env(f"CONN_KEY_{up}"), env(f"CONN_CA_{up}")
    return {"key": key, "cert": (cert, pkey) if cert and pkey else (cert or None), "ca": ca or True}


def source(code):
    c = db.session.get(Connector, code)
    return SOURCE[code] if c is not None and c.environment == "production" else "recette"


# ------------------------------------------------------------------ conversions

def _date_dmy(v):
    d, m, y = str(v).split("/")
    return date(int(y), int(m), int(d)).isoformat()


def _date_iso(v):
    return date.fromisoformat(str(v)[:10]).isoformat()


def _sexe12(v):
    v = str(v).strip().upper()
    if v in ("1", "M", "H", "MASCULIN"):
        return "M"
    if v in ("2", "F", "FEMININ", "FÉMININ"):
        return "F"
    raise ValueError(v)


def _first_year(v):
    return int(str(v)[:4])


CONVERSIONS = {"date_dmy": _date_dmy, "date_iso": _date_iso, "sexe12": _sexe12, "str": str, "int": int,
               "upper_title": lambda v: str(v).strip().title(), "first_year": _first_year}


def _get(obj, path):
    for part in path.split("."):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        elif isinstance(obj, list) and part.isdigit() and int(part) < len(obj):
            obj = obj[int(part)]
        else:
            return None
    return obj


def _map_item(item, fields, required):
    out = {}
    for ours, spec in fields.items():
        path, _, conv = spec.partition("|")
        v = _get(item, path)
        if v is None:
            if ours in required:
                raise FormatError(f"champ « {path} » absent")
            out[ours] = None
            continue
        try:
            out[ours] = CONVERSIONS[conv](v) if conv else v
        except (ValueError, TypeError, KeyError):
            raise FormatError(f"valeur inattendue pour « {path} »")
    return out


def translate(code, body, m=None):
    """Traduit la réponse du partenaire dans le contrat CDEgest (lève FormatError)."""
    m = m or mapping(code)
    req = REQUIRED[code]
    if m.get("list"):
        items = _get(body, m["list"])
        if not isinstance(items, list):
            raise FormatError(f"liste « {m['list']} » absente")
        rows = [_map_item(i, m["fields"], req) for i in items]
        if m.get("pick") == "last":
            return rows[-1] if rows else None
        if m.get("pick") == "first":
            return rows[0] if rows else None
        return rows
    return _map_item(body, m["fields"], req)


# ------------------------------------------------------------------ coupe-circuit

def _failure(c, why):
    c.fail_count = (c.fail_count or 0) + 1
    c.last_error = why[:160]
    if c.fail_count >= CIRCUIT_FAILS and not (c.open_until and c.open_until > utcnow()):
        c.open_until = utcnow() + timedelta(minutes=CIRCUIT_MINUTES)
        AuditLog.log("connector.circuit_open", target=c.code,
                     details=f"{c.fail_count} échecs consécutifs ({why[:80]}) : saisie déclarative pendant {CIRCUIT_MINUTES} min")


def _success(c):
    if c.open_until is not None or (c.fail_count or 0) >= CIRCUIT_FAILS:
        AuditLog.log("connector.circuit_closed", target=c.code, details="service rétabli")
    c.fail_count, c.open_until, c.last_ok_at, c.last_error = 0, None, utcnow(), None


def rearm(code):
    c = connector(code)
    c.fail_count, c.open_until = 0, None


def circuit_open(c):
    return bool(c.open_until and c.open_until > utcnow())


# ------------------------------------------------------------------ appel

def _request(c, url, params, sec, timeout):
    headers = {"Accept": "application/json", "User-Agent": "CDEgest/1.3 (connecteur)"}
    if sec["key"]:
        headers["X-Api-Key"] = sec["key"]
    return requests.get(url, params=params, headers=headers, timeout=(min(3, timeout), timeout),
                        cert=sec["cert"], verify=sec["ca"])


def fetch(code, **values):
    """Interroge le partenaire. Renvoie (statut, données traduites, note pour le journal).

    statut : trouve | inconnu | refuse | indisponible
    """
    c = connector(code)
    if not c.url:
        return "indisponible", None, "aucune adresse configurée"
    if circuit_open(c):
        return "indisponible", None, "coupe-circuit ouvert"
    m = mapping(code)
    try:
        path = m["path"].format(**values)
        params = {k: str(v).format(**values) for k, v in (m.get("params") or {}).items()}
    except (KeyError, IndexError):
        return "indisponible", None, "correspondance : chemin invalide"
    url = c.url.rstrip("/") + path
    sec = secrets(code)
    timeout = max(1, min(30, c.timeout_s or 5))
    t0, tries, last = time.monotonic(), 0, ""
    while tries < MAX_TRIES:
        tries += 1
        try:
            r = _request(c, url, params, sec, timeout)
        except requests.exceptions.Timeout:
            last = "délai dépassé"
        except requests.exceptions.SSLError:
            last = "erreur de certificat"
        except requests.exceptions.ConnectionError:
            last = "serveur injoignable"
        else:
            note = f"HTTP {r.status_code} · {tries} essai{'s' if tries > 1 else ''}"
            if r.status_code == 200:
                try:
                    data = translate(code, r.json(), m)
                except (ValueError, FormatError) as e:
                    _failure(c, f"format inattendu : {e}")
                    return "indisponible", None, f"{note} · format inattendu"
                _success(c)
                return "trouve", data, note
            if r.status_code in (400, 404):
                _success(c)
                return "inconnu", None, note
            if r.status_code in (401, 403):
                c.last_error = f"accès refusé (HTTP {r.status_code}) : vérifier la clé ou le certificat"
                return "refuse", None, note
            last = f"HTTP {r.status_code}"
            if r.status_code < 500 and r.status_code != 429:
                break
        if time.monotonic() - t0 + 0.3 * tries > BUDGET_S:
            break
        time.sleep(0.3 * tries)
    _failure(c, last)
    return "indisponible", None, f"{last} · {tries} essai{'s' if tries > 1 else ''}"


def health(code):
    """« Tester le raccordement » : appel du point de santé du partenaire. Renvoie (ok, message)."""
    c = connector(code)
    if not c.url:
        return False, "aucune adresse configurée"
    sec = secrets(code)
    t0 = time.monotonic()
    try:
        r = _request(c, c.url.rstrip("/") + HEALTH_PATH, {}, sec, max(1, min(30, c.timeout_s or 5)))
    except requests.exceptions.RequestException as e:
        return False, type(e).__name__
    ms = int((time.monotonic() - t0) * 1000)
    if r.status_code == 200:
        return True, f"HTTP 200 en {ms} ms"
    return False, f"HTTP {r.status_code} en {ms} ms"


def status_line(code):
    c = db.session.get(Connector, code)
    if c is None:
        return {}
    return {"url": c.url, "env": c.environment, "timeout": c.timeout_s, "fails": c.fail_count or 0,
            "open": circuit_open(c), "open_until": c.open_until, "last_ok": c.last_ok_at, "error": c.last_error,
            "custom_map": bool(c.mapping), "key": bool(secrets(code)["key"]),
            "mtls": bool(secrets(code)["cert"])}


def configure_from_env():
    """Au démarrage : adresse par défaut des connecteurs entrants (CONN_URL_<CODE> ou CONN_BASE_URL) si vide."""
    n = 0
    for code in INBOUND:
        url = os.environ.get(f"CONN_URL_{code.upper()}") or os.environ.get("CONN_BASE_URL")
        c = connector(code)
        if url and not c.url:
            c.url, n = url, n + 1
    return n


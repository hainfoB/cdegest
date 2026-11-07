"""Échanges avec les administrations (EP-12). Chaque connecteur a trois modes : simulé, réel, désactivé.

En mode simulé, les réponses sont fictives et déterministes (à partir de l'empreinte du NIN) et ne sont
jamais marquées « vérifiées » (RG-41). Le mode réel exige une convention et une adresse configurée :
tant qu'elles n'existent pas, le service est « indisponible » et l'inscription passe en saisie déclarative.
NIN de test : se terminant par 0000 → inconnu ; par 9999 → service indisponible.
"""
import hashlib
import time
from datetime import date, timedelta

from flask_login import current_user

from .. import nin as NIN
from ..extensions import db
from ..models import ApiCall, Connector
from ..utils import utcnow

CONNECTORS = {
    # code: (sens, partenaire fr, partenaire ar, données)
    "etat_civil": ("in", "État civil (ministère de l'Intérieur)", "الحالة المدنية (وزارة الداخلية)",
                   "nom, prénom (arabe, latin), date et lieu de naissance, sexe"),
    "mfep_diplomes": ("in", "SI du MFEP — diplômes", "نظام وزارة التكوين — الشهادات", "diplôme, spécialité, établissement, année"),
    "mfep_stage": ("in", "SI du MFEP — stage pratique", "نظام وزارة التكوين — التربص التطبيقي", "stagiaires en stage, établissement, période"),
    "men": ("in", "Éducation nationale", "التربية الوطنية", "dernier niveau scolaire, année"),
    "nesda": ("in/out", "NESDA", "NESDA", "sortie : formés des sessions validées ; entrée : suite des projets"),
    "mfep_stats": ("out", "SI du MFEP — tableau de bord", "نظام وزارة التكوين — لوحة القيادة", "indicateurs agrégés, sans donnée nominative"),
}
MODES = ("simule", "reel", "desactive")

LAST_M = ["Benali", "Saidi", "Bouzid", "Khelifi", "Mansouri", "Hamdi", "Boudiaf", "Cherif", "Ziani", "Amrani", "Belkacem", "Mebarki"]
LAST_A = ["بن علي", "سعيدي", "بوزيد", "خليفي", "منصوري", "حمدي", "بوضياف", "شريف", "زياني", "عمراني", "بلقاسم", "مباركي"]
FIRST_M = [("Yacine", "ياسين"), ("Amine", "أمين"), ("Karim", "كريم"), ("Walid", "وليد"), ("Sofiane", "سفيان"), ("Nabil", "نبيل")]
FIRST_F = [("Lina", "لينا"), ("Amel", "أمال"), ("Sarah", "سارة"), ("Imane", "إيمان"), ("Meriem", "مريم"), ("Nour", "نور")]
COMMUNES = [("3401", "Bordj Bou Arréridj", "برج بوعريريج"), ("3402", "Ras El Oued", "رأس الوادي"),
            ("1901", "Sétif", "سطيف"), ("2801", "M'Sila", "المسيلة"), ("1601", "Alger-Centre", "الجزائر الوسطى")]
DIPLOMAS = [("BTS", "Informatique — bases de données"), ("BTS", "Comptabilité et gestion"), ("CAP", "Menuiserie"),
            ("BT", "Électricité bâtiment"), ("BTS", "Marketing"), ("CMP", "Pâtisserie")]
LEVELS = [("3AS", "3e année secondaire"), ("4AM", "4e année moyenne"), ("2AS", "2e année secondaire"), ("UNIV", "Universitaire")]


def mode(code):
    c = db.session.get(Connector, code)
    return c.mode if c else "simule"


def set_mode(code, new, user):
    c = db.session.get(Connector, code) or Connector(code=code)
    c.mode, c.updated_by_id, c.updated_at = new, getattr(user, "id", None), utcnow()
    db.session.add(c)
    return c


def _seed(n):
    return int(hashlib.sha256(("sim|" + n).encode()).hexdigest()[:12], 16)


def _log(code, direction, m, nin_hash, fields, result, t0):
    db.session.add(ApiCall(connector=code, direction=direction, mode=m, nin_hash=nin_hash, fields=fields[:200],
                           result=result, duration_ms=int((time.time() - t0) * 1000),
                           user_id=current_user.id if getattr(current_user, "is_authenticated", False) else None))


def _call(code, raw_nin, fields, builder):
    """Appel entrant générique : renvoie (statut, données, source)."""
    t0 = time.time()
    n = NIN.normalize(raw_nin)
    m = mode(code)
    h = NIN.fingerprint(n)
    if m == "desactive":
        _log(code, "in", m, h, fields, "desactive", t0)
        return "desactive", None, "declaratif"
    if m == "reel":
        # aucune adresse ni convention configurée dans le prototype : service indisponible (mode dégradé)
        _log(code, "in", m, h, fields, "indisponible", t0)
        return "indisponible", None, "declaratif"
    if n.endswith("9999"):
        _log(code, "in", m, h, fields, "indisponible", t0)
        return "indisponible", None, "declaratif"
    if n.endswith("0000") or not NIN.valid(n):
        _log(code, "in", m, h, fields, "inconnu", t0)
        return "inconnu", None, "declaratif"
    data = builder(_seed(n))
    _log(code, "in", m, h, fields, "trouve", t0)
    return "trouve", data, "simule"


def identity(raw_nin):
    def b(s):
        female = s % 2 == 0
        fm, fa = (FIRST_F if female else FIRST_M)[(s // 7) % 6]
        k = (s // 11) % len(LAST_M)
        com = COMMUNES[(s // 13) % len(COMMUNES)]
        born = date(1990, 1, 1) + timedelta(days=(s // 17) % (365 * 16))
        return {"nom_lat": LAST_M[k], "prenom_lat": fm, "nom_ar": LAST_A[k], "prenom_ar": fa, "sexe": "F" if female else "M",
                "date_naissance": born.isoformat(), "lieu_naissance": com[0], "commune_fr": com[1], "commune_ar": com[2]}
    return _call("etat_civil", raw_nin, "nom,prenom,naissance,sexe", b)


def diplomas(raw_nin):
    def b(s):
        d = DIPLOMAS[(s // 19) % len(DIPLOMAS)]
        return [{"diplome": d[0], "specialite": d[1], "etablissement": "INSFP-BBA-01", "annee": 2018 + (s // 23) % 8}]
    return _call("mfep_diplomes", raw_nin, "diplomes", b)


def level(raw_nin):
    def b(s):
        lv = LEVELS[(s // 29) % len(LEVELS)]
        return {"niveau": lv[0], "libelle": lv[1], "annee": 2012 + (s // 31) % 12}
    return _call("men", raw_nin, "niveau", b)


def stage_list(institute_code, count=6):
    """Stagiaires en stage pratique d'un établissement (simulé) : NIN fictifs déterministes."""
    t0 = time.time()
    m = mode("mfep_stage")
    if m != "simule":
        _log("mfep_stage", "in", m, None, f"etablissement={institute_code}", "indisponible" if m == "reel" else "desactive", t0)
        return m, []
    out = []
    base = _seed(institute_code)
    for k in range(count):
        n = f"1{(base + k * 7919) % 10**17:017d}"
        st, idt, _src = identity(n)
        if idt:
            out.append({"nin": n, "nom": idt["nom_lat"], "prenom": idt["prenom_lat"], "debut": date.today().isoformat(),
                        "fin": (date.today() + timedelta(days=90)).isoformat()})
    _log("mfep_stage", "in", m, None, f"etablissement={institute_code}", "trouve", t0)
    return "trouve", out


def log_out(code, result, nin_hash=None, fields=""):
    """Trace d'une sortie (données fournies par CDEgest à un partenaire)."""
    _log(code, "out", mode(code), nin_hash, fields, result, time.time())


def apply_identity(obj, status, data, source):
    """Applique la réponse de l'état civil à un dossier (Candidature, Participant ou User)."""
    if status == "trouve" and data:
        if hasattr(obj, "last_name"):
            obj.last_name, obj.first_name = data["nom_lat"], data["prenom_lat"]
        else:
            obj.name = f"{data['prenom_lat']} {data['nom_lat']}"
        obj.sex = data["sexe"]
        obj.birth_date = date.fromisoformat(data["date_naissance"])
        obj.identity_source, obj.identity_checked_at = source, utcnow()
    else:
        obj.identity_source = "declaratif"

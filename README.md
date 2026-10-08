# CDEgest

Plateforme de gestion du réseau des **Centres de développement de l'entrepreneuriat (CDE)** :
institut (INSFP) → wilaya (DFEP, coordinateur) → ministère (MFEP). Trilingue arabe / français / anglais.

Dossier d'architecture : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Avancement
| Étape | Contenu | État |
|---|---|---|
| 1 | Architecture, rôles, droits, indicateurs | ✅ validée |
| 2 | Socle technique, connexion par rôle, i18n, charte CDE | ✅ livrée |
| 3 | Référentiel, objectifs, programme annuel, instituts, comptes, journal | à venir |
| 4 | Sessions, modules, groupes, inscriptions, présence, attestations | à venir |
| 5 | Questionnaire de satisfaction, statut NESDA | à venir |
| 6 | Indicateurs et rapports trimestriels | à venir |
| 7 | Données de démonstration complètes, déploiement Railway | à venir |
| 8 | Recette | à venir |

## Lancer en local
```bash
pip install -r requirements.txt
export FLASK_APP=wsgi
flask db upgrade        # crée la base (SQLite par défaut)
flask seed-base         # wilayas, instituts, comptes de démonstration
flask run               # http://localhost:5000
pytest -q               # tests (dont le cloisonnement par rôle)
```

## Comptes de démonstration (DEMO_MODE=1)
Mot de passe commun : `Cde@2026`

| Rôle | E-mail |
|---|---|
| MFEP | mfep@cdegest.dz |
| DFEP Bordj Bou Arréridj | dfep.bba@cdegest.dz |
| Coordinateur CDE BBA | coord.bba@cdegest.dz |
| Responsable CDE INSFP BBA 01 | resp.insfp-bba01@cdegest.dz |
| Enseignant INSFP BBA 01 | formateur.bba01@cdegest.dz |

## Variables d'environnement (Railway)
| Variable | Rôle |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | longue chaîne aléatoire |
| `APP_URL` | URL publique (active les cookies sécurisés) |
| `DEMO_MODE` | `1` en test (comptes démo affichés), `0` en production |
| `DEMO_PASSWORD` / `ADMIN_PASSWORD` | mots de passe initiaux |

Au démarrage, le `Procfile` applique les migrations puis `seed-base` (idempotent).

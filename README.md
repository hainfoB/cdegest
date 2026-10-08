# CDEgest

Plateforme de gestion du réseau des **Centres de développement de l'entrepreneuriat (CDE)** :
institut (INSFP) → wilaya (DFEP, coordinateur) → ministère (MFEP). Trilingue arabe / français / anglais.

Dossier d'architecture : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Avancement
| Étape | Contenu | État |
|---|---|---|
| 1 | Architecture, rôles, droits, indicateurs | ✅ validée |
| 2 | Socle technique, connexion par rôle, i18n, charte CDE, vue nationale 69 wilayas, comparaison | ✅ livrée |
| 3 | Référentiel, objectifs, programme annuel, instituts, comptes, journal | à venir |
| 4 | Sessions, modules, groupes, inscriptions, présence, attestations | à venir |
| 5 | Questionnaire de satisfaction, statut NESDA | à venir |
| 6 | Indicateurs et rapports trimestriels | à venir |
| 7 | Données de démonstration complètes, déploiement Railway | à venir |
| 8 | Recette | à venir |

## Lancer en local (gratuit)
**Windows** : installer [Python 3.11+](https://www.python.org/downloads/) (cocher *Add Python to PATH*), télécharger le dépôt, puis double-cliquer sur **`demarrer-windows.bat`**.
**Linux / macOS** : `./demarrer.sh`

Au premier lancement, le script installe tout, crée la base locale (SQLite), génère un mot de passe privé par compte dans **`ACCES_LOCAL.txt`** (jamais envoyé sur GitHub) et ouvre http://localhost:5000.

Tests : `pytest -q`

## Mettre en ligne gratuitement (Render + Neon)
1. **Neon** (neon.com) : créer un projet PostgreSQL gratuit, copier l'URL de connexion (`postgresql://…`).
2. **Render** (render.com) : *New → Blueprint*, choisir le dépôt `hainfoB/cdegest` ; le fichier `render.yaml` crée le service.
3. Dans Render, renseigner `DATABASE_URL` (l'URL Neon) et les `PASSWORD_*`.
4. Limites de l'offre gratuite : le service s'endort après 15 min sans visite (≈ 1 min au réveil) ; la base Neon gratuite n'expire pas (1 Go).

## Comptes d'accès
Les comptes ne sont **jamais affichés** sur la page de connexion. Chaque mot de passe vient d'une variable d'environnement Railway ; à défaut, un secret aléatoire est généré (réinitialisable par `flask set-password <email>`).

| Rôle | E-mail | Variable du mot de passe |
|---|---|---|
| MFEP | mfep@cdegest.dz | `PASSWORD_MFEP` |
| DFEP Bordj Bou Arréridj | dfep.bba@cdegest.dz | `PASSWORD_DFEP_BBA` |
| Coordinateur CDE BBA | coord.bba@cdegest.dz | `PASSWORD_COORD_BBA` |
| Responsable CDE INSFP BBA 01 | resp.insfp-bba01@cdegest.dz | `PASSWORD_RESP_BBA01` |
| Enseignant INSFP BBA 01 | formateur.bba01@cdegest.dz | `PASSWORD_ENSEIGNANT_BBA01` |
| Administrateur plateforme | admin@cdegest.dz | `ADMIN_PASSWORD` |

Modifier une variable puis redéployer applique le nouveau mot de passe (`flask sync-passwords` au démarrage).

## Variables d'environnement (Railway)
| Variable | Rôle |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | longue chaîne aléatoire |
| `APP_URL` | URL publique (active les cookies sécurisés) |
| `DEMO_MODE` | `1` : charge les données fictives de Sétif et M'Sila et affiche le bandeau de démonstration |
| `SHOW_DEMO_ACCOUNTS` | laisser à `0` (aucun compte affiché sur la page de connexion) |
| `PASSWORD_*`, `ADMIN_PASSWORD` | mots de passe des comptes (voir ci-dessus) |

Au démarrage, le `Procfile` applique les migrations puis `seed-base` (idempotent).

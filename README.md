# CDEgest

Plateforme de gestion du réseau des **Centres de développement de l'entrepreneuriat (CDE)** :
institut (INSFP) → wilaya (DFEP, coordinateur) → ministère (MFEP). Trilingue arabe / français / anglais.

Dossier d'architecture : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Fonctions
- **7 profils** : MFEP, DFEP, coordinateur CDE de wilaya, responsable CDE d'institut, enseignant intervenant, représentant NESDA de wilaya, DG NESDA (+ administrateur).
- **15 indicateurs** par semestre et par année professionnelle, cibles et statut (atteint, en bonne voie, en retard, non atteint) du CDE jusqu'au national ; vue des 69 wilayas et comparaison jusqu'à 5.
- **Formation** : référentiel, objectifs, programme annuel, sessions avec modules, groupes et créneaux, inscription publique, appel par l'enseignant, abandons.
- **Validation NESDA de la présence** avant l'attestation, imprimable au CDE et vérifiable par QR.
- Satisfaction anonyme, rapports semestriels figés, journal d'audit, trilingue AR/FR/EN, API et widget pour fp.cde.dz.

Détails : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Lancer en local (gratuit)
**Windows** : installer [Python 3.11+](https://www.python.org/downloads/) (cocher *Add Python to PATH*), télécharger le dépôt, puis double-cliquer sur **`demarrer-windows.bat`**.
**Linux / macOS** : `./demarrer.sh`

Au premier lancement (1 à 2 minutes), le script installe tout, crée la base locale (SQLite), charge les données de démonstration fictives, génère un mot de passe privé par compte dans **`ACCES_LOCAL.txt`** (jamais envoyé sur GitHub) et ouvre http://localhost:5000.

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
| Représentant NESDA BBA | nesda.bba@cdegest.dz | `PASSWORD_NESDA_BBA` |
| DG NESDA | dg.nesda@cdegest.dz | `PASSWORD_DG_NESDA` |
| Administrateur plateforme | admin@cdegest.dz | `ADMIN_PASSWORD` |

Modifier une variable puis redéployer applique le nouveau mot de passe (`flask sync-passwords` au démarrage).

## Variables d'environnement (Railway)
| Variable | Rôle |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | longue chaîne aléatoire |
| `APP_URL` | URL publique (active les cookies sécurisés) |
| `DEMO_MODE` | `1` : charge les données fictives de Sétif et M'Sila et affiche le bandeau de démonstration |
| `NESDA_DG_VALIDATION` | `1` : la DG NESDA valide après le représentant de wilaya (par défaut `0`) |
| `SHOW_DEMO_ACCOUNTS` | laisser à `0` (aucun compte affiché sur la page de connexion) |
| `PASSWORD_*`, `ADMIN_PASSWORD` | mots de passe des comptes (voir ci-dessus) |

Au démarrage, le `Procfile` applique les migrations puis `seed-base` (idempotent).

# CDEgest

Plateforme de gestion du réseau des **Centres de développement de l'entrepreneuriat (CDE)** :
institut (INSFP) → wilaya (DFEP, coordinateur) → ministère (MFEP). Trilingue arabe / français / anglais.

Dossier d'architecture : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Fonctions
- **v1.3 — identité par NIN** : toute personne (agents, candidats, stagiaires) se connecte avec son NIN, son mot de passe et un code à usage unique (e-mail, SMS ou WhatsApp) ; un compte peut porter plusieurs habilitations, le rôle actif est choisi à la connexion.
- **v1.3 — messages** : 18 messages (M-01 à M-18) en 4 catégories, heures calmes, plafond quotidien, résumé quotidien des agents ; boîte d'envoi simulée (aucun envoi réel dans le prototype).
- **v1.3 — échanges avec l'État** : état civil, MFEP (diplômes, stage pratique, statistiques), Éducation nationale, NESDA (formés, suite des projets) ; connecteurs simulé / réel / désactivé, journal des échanges sans NIN en clair.
- **7 profils** : MFEP, DFEP, coordinateur CDE de wilaya, responsable CDE d'institut, enseignant intervenant, représentant NESDA de wilaya, DG NESDA (+ administrateur).
- **15 indicateurs** par semestre et par année professionnelle, cibles et statut (atteint, en bonne voie, en retard, non atteint) du CDE jusqu'au national ; vue des 69 wilayas et comparaison jusqu'à 5.
- **Formation** : référentiel, objectifs, programme annuel, sessions avec modules, groupes et créneaux, inscription publique, appel par l'enseignant, abandons.
- **Validation NESDA de la présence** avant l'attestation, imprimable au CDE et vérifiable par QR.
- Satisfaction anonyme, rapports semestriels figés, journal d'audit, trilingue AR/FR/EN, API et widget pour fp.cde.dz.

Détails : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Lancer en local (gratuit)
**Windows** : installer [Python 3.10+](https://www.python.org/downloads/) (cocher *Add python.exe to PATH*), télécharger le dépôt, puis double-cliquer sur **`demarrer-windows.bat`**.
- `demarrer-reseau-windows.bat` : même chose, accessible depuis un téléphone sur le même Wi-Fi (adresse affichée).
- `reinitialiser-demo-windows.bat` : efface et recrée les données de démonstration (à lancer le jour d'une présentation, pour que l'appel « du jour » existe).
- Si un dossier `wheels/` est présent, l'installation se fait sans Internet.
**Linux / macOS** : `./demarrer.sh`

Au premier lancement (1 à 2 minutes), le script installe tout, crée la base locale (SQLite), charge les données de démonstration fictives, génère un mot de passe privé par compte dans **`ACCES_LOCAL.txt`** (jamais envoyé sur GitHub) et ouvre http://localhost:5000.

Tests : `pytest -q`

## Mettre en ligne gratuitement (Render + Neon)
1. **Neon** (neon.com) : créer un projet PostgreSQL gratuit, copier l'URL de connexion (`postgresql://…`).
2. **Render** (render.com) : *New → Blueprint*, choisir le dépôt `hainfoB/cdegest` ; le fichier `render.yaml` crée le service.
3. Dans Render, renseigner `DATABASE_URL` (l'URL Neon) et les `PASSWORD_*`.
4. Limites de l'offre gratuite : le service s'endort après 15 min sans visite (≈ 1 min au réveil) ; la base Neon gratuite n'expire pas (1 Go).

## Comptes d'accès
Identifiant = **NIN** (fictif). Chaque mot de passe vient d'une variable d'environnement ; à défaut, un secret aléatoire (réinitialisable par `flask set-password <NIN>`). Les comptes d'agents reçoivent un code à chaque connexion ; en démonstration, le code simulé s'affiche sous le champ.

| Personne | NIN | Habilitations | Variable du mot de passe |
|---|---|---|---|
| Direction centrale MFEP | 109900000000001012 | MFEP | `PASSWORD_MFEP` |
| DFEP Bordj Bou Arréridj | 109934000000002013 | DFEP (wilaya 34) | `PASSWORD_DFEP_BBA` |
| Coordinateur CDE BBA | 109934000000003014 | coordinateur (34) + enseignant (INSFP BBA 02) | `PASSWORD_COORD_BBA` |
| Responsable CDE INSFP BBA 01 | 109934010000004015 | responsable + enseignant (INSFP BBA 01) | `PASSWORD_RESP_BBA01` |
| Enseignante INSFP BBA 01 | 109934010000005016 | enseignante (BBA 01 et BBA 02) | `PASSWORD_ENSEIGNANT_BBA01` |
| Représentant NESDA BBA | 109934000000006017 | NESDA (34) | `PASSWORD_NESDA_BBA` |
| Direction générale NESDA | 109900000000007018 | DG NESDA | `PASSWORD_DG_NESDA` |
| Candidate de démonstration (Lina Saidi) | 100234000000012024 | candidat + stagiaire | `PASSWORD_CANDIDAT_DEMO` |
| Administrateur plateforme | 109900000000000011 | administrateur | `ADMIN_PASSWORD` |

Modifier une variable puis redéployer applique le nouveau mot de passe (`flask sync-passwords` au démarrage).
NIN de test pour les connecteurs simulés : terminé par `0000` = inconnu de l'état civil, par `9999` = service indisponible.

Tâches planifiées (production) : `flask notify-run` toutes les heures (envois programmés et rappels), `flask notify-digest` à 8 h les jours ouvrables.

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
| `NIN_KEY` | clé de chiffrement et d'empreinte des NIN (par défaut dérivée de `SECRET_KEY`) |
| `NESDA_API_KEY`, `MFEP_API_KEY` | clés des API de sortie (vides = API fermées) |
| `SHOW_SIMULATED_MESSAGES` | `1` en démonstration : affiche le message simulé (code) à l'écran ; `0` en production |

Au démarrage, le `Procfile` applique les migrations, recrée une seule fois la base de démonstration v1.3 (`reset-demo --if-version 1.3`, uniquement si `DEMO_MODE=1`), puis `seed-base` (idempotent).

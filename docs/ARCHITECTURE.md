# CDEgest — Dossier d'architecture (Étape 1)

> Plateforme de gestion du réseau des Centres de développement de l'entrepreneuriat (CDE) : de l'institut (INSFP) à la wilaya (DFEP), jusqu'au ministère (MFEP).
> Version 1.5 — 8 octobre 2026 — à valider avant l'étape 2.

---

## 1. Décisions déjà prises

| Sujet | Décision |
|---|---|
| Socle | Reprise du cœur éprouvé de `centre-formation` (sessions, inscriptions, liste d'attente, 4 modes de présence, créneaux), réécrit en architecture modulaire |
| Paiements / caisse | **Supprimés** : toutes les activités CDE sont gratuites |
| Notifications | WhatsApp (liens `wa.me` pré-remplis, partout) + e-mail (Brevo, activé si la clé est fournie) |
| Langues | Arabe (RTL, langue par défaut), français, anglais |
| Territoire | **69 wilayas** (codes 59 à 69 : décret présidentiel n° 26-206 du 25 mai 2026), toutes chargées en base |
| Démo | Bordj Bou Arréridj (wilaya pilote) + Sétif et M'Sila avec **données fictives** clairement signalées |
| Période | **Année professionnelle** de septembre à août (mois de début paramétrable), découpée en **2 semestres** : S1 septembre–février, S2 mars–août. Les KPI (dont le nombre de groupes) sont mesurés **par semestre et par année professionnelle** |
| Hébergement | Railway (service web + PostgreSQL), dépôt `hainfoB/cdegest` |
| Mission | **Le CDE forme.** L'accompagnement des porteurs de projet relève de la NESDA : CDEgest ne le gère pas, il **enregistre seulement le résultat** (dossier accepté, projet abouti) communiqué par la NESDA, pour mesurer la conversion |
| Satisfaction | Questionnaire de fin de session, anonyme, depuis le ticket du participant |
| DFEP | **Mêmes prérogatives que le coordinateur** sur sa wilaya |
| Charte | Celle de fp.cde.dz : vert CDE `#07E5BB`, encre `#0D1B2A`, blanc ; logo CDE en cercle de points |

---

## 2. Hiérarchie et utilisateurs

```
MFEP (national)
 └── Wilaya ── DFEP (directeur / service)
      └── Coordinateur CDE de wilaya
           └── INSFP ── Responsable CDE de l'institut
                 └── Formateurs
                       └── Participants (stagiaires, diplômés) — sans compte
```

| Code rôle | Libellé | Périmètre | Compte démo |
|---|---|---|---|
| `admin` | Administrateur plateforme | Tout (technique) | `admin@cdegest.dz` |
| `mfep` | MFEP — Direction centrale | National, **agrégé** | `mfep@cdegest.dz` |
| `dfep` | DFEP de wilaya | Sa wilaya (mêmes droits que le coordinateur, plus la validation) | `dfep.bba@cdegest.dz` |
| `coord` | Coordinateur CDE de wilaya | Sa wilaya | `coord.bba@cdegest.dz` |
| `resp` | Responsable CDE de l'institut | Son institut | `resp.insfp-bba01@cdegest.dz` |
| `formateur` | Enseignant intervenant | Les modules qu'il supervise et les créneaux qu'il anime ; **fait l'appel** dans ses séances | `formateur.bba01@cdegest.dz` |

Les participants n'ont pas de compte : ils s'inscrivent par lien public et reçoivent un **ticket personnel** (lien secret + QR) qui donne accès à leurs présences et à leur attestation.

Mot de passe démo commun affiché uniquement en environnement de test (`DEMO_MODE=1`), désactivé en production.

---

## 3. Matrice des droits

Légende : **G** = gère (créer/modifier) · **V** = valide · **L** = lit (nominatif) · **A** = lit en agrégé seulement · — = aucun accès

| Objet | MFEP | DFEP | Coord. | Resp. CDE | Formateur |
|---|---|---|---|---|---|
| Référentiel national (catalogue de formations, indicateurs, modèle d'attestation) | G | L | L | L | L |
| Objectifs annuels par wilaya et par CDE (saisis à l'ouverture de l'année professionnelle) | G | L + répartit entre ses CDE | L | L (son CDE) | — |
| Comparaison de wilayas (jusqu'à 5, tous les KPI) | G | — | — | — | — |
| Programme annuel de wilaya | A | G + **V** | G | L | — |
| Instituts et comptes de la wilaya | — | G (resp., formateurs) | G (resp., formateurs) | G (formateurs de l'institut) | — |
| Pool de formateurs mutualisés | — | G | G | L, demande | — |
| Sessions de l'institut | A | L | L | G | L (celles où il intervient) |
| Modules (contenu, supervision) | A | L | L | G (affecte les superviseurs) | G (contenu et suivi des modules qu'il supervise) |
| Événements de wilaya | A | G | G | L | L (s'il intervient) |
| Inscriptions et participants | — | L | L | G | L (groupes de ses modules) |
| Présence | A | L | L | G (correction) | **G : fait l'appel** de ses créneaux, lecture sur ses modules |
| Attestations | A | L | L | G (délivrance) | — |
| Suites NESDA (dossier déposé / accepté / abouti) | A | L | L | G (saisie) | — |
| Questionnaires de satisfaction | Modèle : G ; résultats : A | A | A | A (+ commentaires anonymes) | A (ses séances) |
| Rapport semestriel institut | A | V (consolide) | V (consolide) | G puis V, transmet | — |
| Rapport semestriel wilaya | L | G + V, transmet | G | — | — |
| Tableau de bord | National : les 69 wilayas et tous les CDE, avec statut des objectifs | Wilaya, institut par institut | Wilaya, institut par institut | Institut | Ses séances |
| Journal d'audit | L (actions MFEP) | L (sa wilaya) | L (sa wilaya) | L (son institut) | — |

**Règle de cloisonnement (loi n° 18-07)** : le MFEP ne voit **jamais** de nom, de téléphone ni d'e-mail de participant. Toutes ses vues passent par des agrégats calculés côté serveur. Un filtre de périmètre unique (`scope_query`) est appliqué à chaque requête selon le rôle ; aucun écran ne fait de requête « brute ».

---

## 4. Circuits de validation

### 4.1 Circuit annuel
1. **MFEP**, à l'ouverture de l'année professionnelle, publie le référentiel et saisit les objectifs de l'année pour chaque wilaya (et, s'il le souhaite, directement pour certains CDE).
1 bis. **DFEP** répartit l'objectif de sa wilaya entre ses CDE (la somme est contrôlée).
2. **Coordinateur** rédige le programme annuel de la wilaya (formations du catalogue × instituts × semestres).
3. **DFEP** valide (ou renvoie avec observations).
4. **Responsable CDE** planifie les sessions dans son institut, rattachées aux lignes du programme.
5. **Formateurs** animent et pointent la présence.
6. Le **système** calcule les indicateurs en continu.

### 4.2 Rapport semestriel (remontée)
```
Institut : brouillon → validé par le resp. → transmis au coordinateur
Wilaya   : consolidation (quand tous les instituts ont transmis, ou forcée) → brouillon → validé par la DFEP → transmis au MFEP
National : reçu par le MFEP → tableau national mis à jour
```
Chaque rapport transmis est **figé** (instantané des chiffres + date + signataire) : un chiffre corrigé plus tard n'altère pas un rapport déjà remonté. Export PDF et Excel à chaque niveau.

### 4.3 Structure d'une session
```
Session (ex. « Initiation à l'entrepreneuriat », INSFP BBA 01, 2026-T4)
 ├── Modules  ── chacun a UN enseignant superviseur et un volume horaire
 │     M1 Idée et marché ............ superviseur : Ens. A
 │     M2 Modèle économique ......... superviseur : Ens. B
 │     M3 Statut et démarches ....... superviseur : Ens. C
 ├── Groupes  ── G1, G2, G3… (participants répartis)
 └── Séances  ── par groupe, découpées en créneaux
       Créneau = module + enseignant intervenant + horaire
```
Règles :
- Une session a **plusieurs groupes** et **plusieurs enseignants intervenants**.
- Chaque enseignant affecté à une session **supervise au moins un module** : la session ne peut pas être ouverte aux inscriptions tant qu'un intervenant n'a aucun module.
- Un module a **un seul superviseur**, mais peut être animé par d'autres intervenants selon les groupes (le superviseur reste responsable du contenu et du suivi).
- La présence est enregistrée par créneau, donc les heures se ventilent automatiquement par module, par groupe et par enseignant.

### 4.4 L'appel par l'enseignant
L'enseignant ouvre sa séance (seulement le jour même, seulement ses créneaux) et voit la liste nominative du groupe :
- un geste par participant : **présent / absent / en retard / excusé** ; « tous présents » en un clic puis on décoche les absents ;
- heure d'arrivée et de départ modifiables pour un retard ou un départ anticipé ;
- les modes QR (ticket, QR de salle) et le code en ligne restent disponibles en complément ; l'appel de l'enseignant fait foi ;
- l'appel est **verrouillé** à la fin de la journée ; seul le responsable CDE peut ensuite le corriger (correction tracée au journal).

### 4.5 Statut des objectifs (wilayas et CDE)
Calculé indicateur par indicateur, puis résumé par wilaya et par CDE :

| Statut | Règle (en cours d'année) | Règle (année close) |
|---|---|---|
| Atteint | réalisé ≥ 100 % de la cible | réalisé ≥ 100 % |
| En bonne voie | réalisé ≥ cible × part de l'année écoulée | — |
| En retard | réalisé < cible × part de l'année écoulée | — |
| Non atteint | — | réalisé < 100 % |
| Non fixé | aucune cible saisie | aucune cible saisie |

Pour les indicateurs « plus bas = mieux » (taux de déperdition), la comparaison est inversée. Le statut global d'une wilaya ou d'un CDE = proportion de ses objectifs atteints ou en bonne voie (seuil paramétrable, par défaut 80 %).

### 4.6 Vue nationale du MFEP
- Tableau des **69 wilayas** : CDE, groupes, formés, assiduité, statut des objectifs ; recherche et filtre par statut (atteint, en bonne voie, en retard, non atteint, non fixé).
- Descente wilaya → liste de ses CDE avec leur propre statut.
- **Comparaison de 2 à 5 wilayas** côte à côte sur les 15 indicateurs, avec cible et statut de chacun.
- Toujours sans donnée nominative.

### 4.7 Statuts d'une session (repris de l'existant)
Brouillon → Inscriptions ouvertes → En cours (inscriptions fermées) → Terminée.

---

## 5. Indicateurs (KPI) communs — définitions calculées

Période = semestre ou année professionnelle ; périmètre = institut, wilaya ou national. Chaque indicateur est affiché avec sa **cible** (objectif MFEP) et son taux de réalisation, ventilable par institut, thème et sexe.

### 5.1 Activité de formation
| # | Indicateur | Définition exacte |
|---|---|---|
| 1 | Groupes formés | Groupes ayant terminé leur dernière séance dans le semestre ; cumul sur l'année professionnelle (une session compte un ou plusieurs groupes). Cible fixée par semestre et par année |
| 2 | Sessions réalisées | Sessions passées au statut « Terminée » dans la période |
| 3 | Participants formés | Participants distincts présents à au moins une séance |
| 4 | Enseignants mobilisés | Enseignants distincts intervenus dans au moins un créneau ; affiché avec le nombre de modules supervisés |
| 5 | Heures de formation suivies | Somme des minutes réellement suivies (entrée → sortie, par créneau) ÷ 60 |
| 6 | Taux de remplissage | Inscrits confirmés ÷ places offertes |

### 5.2 Assiduité et déperdition
| # | Indicateur | Définition exacte |
|---|---|---|
| 7 | Taux d'assiduité | Présences ÷ présences attendues des inscrits confirmés |
| 8 | Nombre d'abandons | Inscrits confirmés ayant suivi au moins une séance, puis : désistement déclaré **ou** absents aux 2 dernières séances (seuil paramétrable) **ou** sous le seuil d'assiduité à la clôture |
| 9 | Taux de déperdition | Abandons ÷ inscrits confirmés ayant commencé la formation |
| 10 | Attestations délivrées | Attestations émises (participants ayant atteint le seuil) |

### 5.3 Conversion (résultats communiqués par la NESDA)
| # | Indicateur | Définition exacte |
|---|---|---|
| 11 | Projets acceptés | Participants formés dont le dossier est marqué « accepté NESDA » |
| 12 | Taux de conversion | Projets acceptés ÷ participants formés (même cohorte) |
| 13 | Projets aboutis | Projets marqués « abouti » (entreprise créée) |

Le responsable CDE saisit pour chaque participant un simple statut : *non déposé → déposé → accepté → abouti*, avec la date. Pas de fiche projet, pas de mentorat : seulement la trace du résultat.

### 5.4 Qualité
| # | Indicateur | Définition exacte |
|---|---|---|
| 14 | Taux de satisfaction | Part des réponses « satisfait » ou « très satisfait » à la question globale |
| 15 | Taux de réponse | Questionnaires remplis ÷ participants présents à la dernière séance |

**Questionnaire de satisfaction** : modèle unique défini par le MFEP (8 à 10 questions : contenu, formateur, organisation, utilité, note globale, commentaire libre), envoyé automatiquement après la dernière séance via le ticket du participant. Réponses **anonymes** (le lien au participant sert seulement à empêcher une double réponse).

## 6. Modèle de données

```
Wilaya ─< Institute ─< User (resp, formateur)
   │          │
   │          └─< Session ─< Module (superviseur)
   │                 ├─< SessionTeacher (intervenants)
   │                 ├─< Group ─< Seance ─< Slot (module + intervenant + horaire)
   │                 │          └─< Attendance (par inscription : entrée, sortie, statut, méthode)
   │                 ├─< SurveyResponse (anonyme)
   │                 └─< Enrollment >─ Participant ─── statut NESDA
   ├─< Objective (année, indicateur, cible)
   ├─< Programme ─< ProgrammeLine >─ WorkshopTemplate (catalogue MFEP)
   └─< Report (niveau, semestre, statut, instantané JSON)
```

Tables principales :

| Table | Champs clés |
|---|---|
| `wilaya` | code (34), nom_fr, nom_ar, is_demo |
| `institute` | wilaya_id, code (`INSFP-BBA-01`), nom_fr, nom_ar, adresse, cde_ouvert_le |
| `user` | nom, e-mail, téléphone, rôle, wilaya_id, institute_id, langue, actif, dernière connexion |
| `workshop_template` | thème, titre/objectifs FR+AR, durée, type (atelier, bootcamp, séminaire, événement) |
| `objective` | année professionnelle, wilaya_id, institute_id (facultatif), indicateur, cible, saisi_par, saisi_le |
| `programme` / `programme_line` | wilaya, année, statut, validé_par / atelier, institut, semestre, nb prévu |
| `session` | institut **ou** wilaya (événement), formation du catalogue, mode, lieu/lien, places, seuil d'assiduité, contrôle entrée/sortie, confirmation auto, statut |
| `seance` / `slot` | groupe, date, horaire / module, enseignant intervenant, début, fin, jetons de scan, codes d'entrée/sortie |
| `participant` | nom, prénom, e-mail, téléphone, wilaya, institut d'origine, spécialité, année de diplôme, statut (stagiaire / diplômé), **consentement** (date) |
| `module` | session, ordre, titre FR+AR, volume horaire, **superviseur** (enseignant) |
| `session_teacher` | session, enseignant (contrôle : ≥ 1 module supervisé) |
| `group` | session, nom (G1, G2…), places, salle ou lien |
| `enrollment` | session, groupe, participant, statut, source, jeton du ticket, n° d'attestation, **abandon** (oui/non, date, motif, détection auto/manuelle) |
| `participant` (suite) | statut NESDA (non déposé / déposé / accepté / abouti), date du statut |
| `survey_template` / `survey_response` | questions FR+AR+EN / session, réponses JSON, date (sans identité stockée) |
| `attendance` | séance, inscription, statut, entrée, sortie, méthode |
| `report` | niveau, périmètre, année professionnelle, semestre (1 ou 2), statut, instantané, validé_par, transmis_le |
| `audit_log` | utilisateur, action, objet, détails, date, IP |

Conservation : purge (anonymisation) des données nominatives des participants N années après leur dernière activité — durée paramétrable par le MFEP.

---

## 7. Architecture technique

| Couche | Choix | Pourquoi |
|---|---|---|
| Langage / framework | Python 3.12, Flask 3 | Continuité avec vos applications existantes |
| Base | PostgreSQL (Railway), SQLite en local | Robuste, gratuit en phase test |
| ORM / migrations | SQLAlchemy 2 + **Flask-Migrate (Alembic)** | Migrations versionnées (au lieu de l'auto-migration maison) |
| Sécurité | Flask-Login, CSRF (Flask-WTF), mots de passe hachés, anti-force brute, en-têtes de sécurité, cookies sécurisés | Repris et renforcé |
| Organisation du code | Blueprints : `auth`, `org`, `referentiel`, `programme`, `sessions`, `presence`, `public`, `rapports`, `dashboard` | Lisible, testable, chaque rôle a son module |
| Tâches planifiées | APScheduler (rappels veille de séance, détection des abandons, envoi du questionnaire, relance des rapports en retard) | Déjà maîtrisé |
| Documents | openpyxl (Excel), ReportLab + arabic-reshaper + python-bidi (PDF arabe), segno (QR) | PDF bilingues corrects en arabe |
| Interface | Jinja + CSS maison (pas de framework lourd), RTL natif, police Tajawal (AR) / Poppins (FR, EN) | Rapide sur mobile et réseau faible |
| Tests | pytest : un jeu de tests **par rôle** vérifiant qu'aucune donnée hors périmètre n'est accessible | Le cloisonnement est le point critique |
| Démo | Commande `flask seed-demo` : 3 wilayas, 5 INSFP, comptes, sessions à tous les statuts, présences, attestations | Recréable à volonté |

Arborescence prévue :
```
cdegest/
├── app/
│   ├── __init__.py          # fabrique d'application
│   ├── models/              # un fichier par domaine
│   ├── security/            # rôles, périmètres, décorateurs
│   ├── blueprints/          # auth, org, referentiel, programme, sessions, presence, public, rapports, dashboard
│   ├── services/            # indicateurs, rapports, notifications, pdf, qr
│   ├── i18n/                # ar.json, fr.json, en.json
│   ├── templates/
│   └── static/              # css, img/logo-cde.png
├── migrations/
├── seeds/demo.py
├── tests/
├── docs/
├── Procfile · requirements.txt · railway.json · README.md
```

---

## 8. Ce qui sort du périmètre de la v1

- Application mobile native (le site est conçu mobile d'abord, suffisant pour le scan).
- Accompagnement, mentorat et suivi des porteurs de projet : **mission de la NESDA**, non géré par CDEgest.
- Connexion aux systèmes du ministère ou de la NESDA (export Excel à la place).
- Signature électronique des rapports (validation tracée par compte + date à la place).

---

## 9. Points à valider

1. La liste des rôles et leur périmètre (section 2).
2. La matrice des droits (section 3) : MFEP en agrégé uniquement, DFEP = coordinateur + validation.
3. Le circuit de remontée des rapports (section 4.2).
4. Les 15 indicateurs et la règle de détection des abandons (section 5).
5. Les wilayas de comparaison : Sétif et M'Sila avec données fictives.

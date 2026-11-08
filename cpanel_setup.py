"""Installation et mise à jour de CDEgest sur un hébergement cPanel (à lancer après chaque mise à jour).

Dans cPanel → « Setup Python App » → votre application → « Execute python script » : cpanel_setup.py
(adresses lues dans les variables APP_URL et SIM_URL de l'application si elles existent),
ou dans le Terminal de cPanel, environnement de l'application activé :
    python cpanel_setup.py --url https://cdegest.mondomaine.dz --sim-url https://sim.mondomaine.dz

Étapes : .env (créé ou complété, jamais écrasé) → base de données → données (démonstration si DEMO_MODE=1)
→ mots de passe → raccordement des connecteurs → redémarrage de l'application. Accès : ACCES_LOCAL.txt.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def flask(*args, check=True):
    print(f"\n» flask {' '.join(args)}", flush=True)
    r = subprocess.run([sys.executable, "-m", "flask", "--app", "wsgi", *args], cwd=HERE)
    if check and r.returncode != 0:
        sys.exit(f"Échec de l'étape « {' '.join(args)} ». Copiez ce message pour l'assistance.")
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("APP_URL", ""), help="adresse publique, ex. https://cdegest.mondomaine.dz")
    ap.add_argument("--sim-url", default=os.environ.get("SIM_URL") or None, help="adresse du simulateur (recette) ; omis = aucun simulateur")
    a = ap.parse_args()
    if sys.version_info < (3, 10):
        sys.exit("Python 3.10 ou plus récent est requis : choisissez une version plus récente dans « Setup Python App ».")
    init = ["init-local", "--sim-url", a.sim_url or ""]
    if a.url:
        init += ["--url", a.url.rstrip("/")]
    flask(*init)
    flask("db", "upgrade")
    flask("reset-demo", "--if-version", "1.3.1")
    flask("seed-base")
    flask("seed-demo")
    flask("sync-passwords")
    flask("connectors-env", check=False)
    os.makedirs(os.path.join(HERE, "tmp"), exist_ok=True)
    with open(os.path.join(HERE, "tmp", "restart.txt"), "w") as f:      # Passenger : redémarrer l'application
        f.write("restart\n")
    print("\nTerminé. Application redémarrée. Accès : fichier ACCES_LOCAL.txt (dossier de l'application).")


if __name__ == "__main__":
    main()

"""Simulateur d'administrations sur cPanel : application Python distincte (sous-domaine), racine = ce dossier.

Clé d'accès : variable SIM_API_KEY (dans « Environment variables » de l'application, ou fichier .env ici).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
env = os.path.join(HERE, ".env")
if os.path.exists(env):
    for line in open(env, encoding="utf-8"):
        k, sep, v = line.strip().partition("=")
        if sep and not k.startswith("#"):
            os.environ.setdefault(k.strip(), v.strip())

from app import app as application  # noqa: E402

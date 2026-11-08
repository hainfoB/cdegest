"""Point d'entrée pour cPanel (« Setup Python App », Phusion Passenger).

Le fichier .env est chargé AVANT l'import de l'application : la configuration le lit au démarrage.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, ".env"))
except ImportError:
    pass

from wsgi import app as application  # noqa: E402

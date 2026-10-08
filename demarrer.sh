#!/usr/bin/env bash
# CDEgest — lancement local (Linux / macOS)
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || flask --app wsgi init-local
flask --app wsgi db upgrade
flask --app wsgi seed-base
flask --app wsgi sync-passwords
echo "CDEgest : http://localhost:5000  (accès : ACCES_LOCAL.txt)"
flask --app wsgi run --port 5000

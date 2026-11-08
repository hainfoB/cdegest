#!/usr/bin/env bash
# CDEgest v1.3 — lancement local (Linux / macOS) : application + simulateur d'administrations
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements-local.txt
flask --app wsgi init-local --sim-url http://127.0.0.1:5099
flask --app simulateur.app run --port 5099 > simulateur.log 2>&1 &
SIM=$!
trap 'kill $SIM 2>/dev/null' EXIT
flask --app wsgi db upgrade
flask --app wsgi reset-demo --if-version 1.3.1
flask --app wsgi seed-base
flask --app wsgi seed-demo
flask --app wsgi sync-passwords
flask --app wsgi connectors-env || true
echo "CDEgest : http://localhost:5000  (accès : ACCES_LOCAL.txt)"
flask --app wsgi run --port 5000

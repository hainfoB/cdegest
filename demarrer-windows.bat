@echo off
chcp 65001 >nul
title CDEgest - serveur local
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11 ou plus recent est requis : https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv (
  echo Installation de l'environnement Python...
  python -m venv .venv || (pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt || (pause & exit /b 1)
if not exist .env python -m flask --app wsgi init-local
python -m flask --app wsgi db upgrade || (pause & exit /b 1)
python -m flask --app wsgi seed-base
python -m flask --app wsgi sync-passwords
echo.
echo CDEgest demarre sur http://localhost:5000  (vos acces : ACCES_LOCAL.txt)
echo Fermez cette fenetre pour arreter le serveur.
start "" http://localhost:5000/login
python -m flask --app wsgi run --port 5000
pause

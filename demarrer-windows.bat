@echo off
setlocal
chcp 65001 >nul
title CDEgest - serveur local
cd /d "%~dp0"
set MODE=%1

echo.
echo  ===============================================
echo   CDEgest - plateforme de gestion du reseau CDE
echo  ===============================================
echo.

rem ---- 1. Python
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto oldpython

rem ---- 2. Environnement et bibliotheques (une seule fois)
if exist ".venv\Scripts\python.exe" goto venvok
echo  [1/5] Creation de l'environnement Python...
%PY% -m venv .venv
if errorlevel 1 goto failed
:venvok
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -c "import flask, flask_sqlalchemy, flask_migrate, flask_login, flask_wtf, segno, openpyxl, dotenv, cryptography, requests" >nul 2>nul
if not errorlevel 1 goto libsok
echo  [2/5] Installation des bibliotheques...
if not exist "wheels" goto online
"%VPY%" -m pip install -q --no-index --find-links wheels -r requirements-local.txt
if not errorlevel 1 goto libsok
echo        (installation hors ligne impossible, tentative par Internet)
:online
"%VPY%" -m pip install -q -r requirements-local.txt
if errorlevel 1 goto failed
:libsok

rem ---- 3. Acces, simulateur d'administrations et base de donnees
if /i "%MODE%"=="reset" (
  echo  Reinitialisation de la demonstration...
  if exist "instance\cdegest.db" del /q "instance\cdegest.db"
)
rem .env : cree la premiere fois, complete lors d'une mise a jour (les mots de passe existants sont gardes)
"%VPY%" -m flask --app wsgi init-local --sim-url http://127.0.0.1:5099
if errorlevel 1 goto failed
echo  [3/5] Demarrage du simulateur d'administrations (fenetre reduite)...
start "CDEgest - simulateur d'administrations" /min "%VPY%" -m flask --app simulateur.app run --port 5099
echo  [4/5] Preparation de la base (premiere fois : environ 1 minute)...
"%VPY%" -m flask --app wsgi db upgrade >nul 2>nul
if errorlevel 1 goto failed
"%VPY%" -m flask --app wsgi reset-demo --if-version 1.3.1
if errorlevel 1 goto failed
"%VPY%" -m flask --app wsgi seed-base >nul
"%VPY%" -m flask --app wsgi seed-demo >nul
"%VPY%" -m flask --app wsgi sync-passwords >nul
"%VPY%" -m flask --app wsgi connectors-env

rem ---- 4. Serveur
echo.
echo  [5/5] CDEgest v1.3 est pret : http://localhost:5000
echo        Acces (NIN et mots de passe) : fichier ACCES_LOCAL.txt
echo        Echanges avec l'Etat : mode reel, vers le simulateur (fenetre reduite, a laisser ouverte)
if /i "%MODE%"=="reseau" (
  echo.
  echo        Depuis un telephone sur le meme Wi-Fi, ouvrez :
  "%VPY%" -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('10.255.255.255', 1)); print('        http://' + s.getsockname()[0] + ':5000')" 2>nul
  echo        Si Windows demande l'autorisation du pare-feu, acceptez pour les reseaux prives.
)
echo.
echo        Laissez cette fenetre ouverte pendant la demonstration.
echo        Fermez-la (et celle du simulateur) pour arreter CDEgest.
echo.
start "" http://localhost:5000/login
if /i "%MODE%"=="reseau" (
  "%VPY%" -m flask --app wsgi run --host 0.0.0.0 --port 5000
) else (
  "%VPY%" -m flask --app wsgi run --port 5000
)
goto end

:nopython
echo  Python n'est pas installe sur ce PC.
echo  1. Telechargez Python 3.12 : https://www.python.org/downloads/
echo  2. Pendant l'installation, cochez "Add python.exe to PATH".
echo  3. Relancez ce fichier.
goto end
:oldpython
echo  Python 3.10 ou plus recent est requis. Installez Python 3.12 : https://www.python.org/downloads/
goto end
:failed
echo.
echo  Une etape a echoue. Faites une capture de cette fenetre pour l'assistance.
:end
echo.
pause

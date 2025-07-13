@echo off
cd /d "%~dp0"
REM === Vérification de Python ===
python --version >nul 2>&1

IF %ERRORLEVEL% NEQ 0 (
    echo Python n'est pas installé sur ce système.
    echo Téléchargement depuis le site officiel...
    start https://www.python.org/downloads/windows/
    echo Une fois installé, relance ce fichier.
    pause
    exit
) ELSE (
    echo Python est installe
)

REM === Installation des dépendances ===
IF EXIST requirements.txt (
    echo Installation des bibliotheques...
    pip install -r requirements.txt
) ELSE (
    echo Le fichier requirements.txt est introuvable.
    echo Dépendances necessaires :
    echo numpy, scipy, pyserial, pyAudioWpatch
)

REM === Lancement du script beat.py ===
echo Lancement du programme...
python beat.py ^
    --port COM7 ^
    --baudrate 115200 ^
    --bp-low 30 ^
    --bp-high 100 ^
    --k-high 1.4 ^
    --k-low 0.9 ^
    --min-interval 0.4

REM === Fin ===
pause


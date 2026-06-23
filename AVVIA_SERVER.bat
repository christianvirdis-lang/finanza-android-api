@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Server finanza in ascolto su tutte le interfacce, porta 5050...
echo Sul telefono (stessa rete Wi-Fi) l'app si collega a questo PC.
echo Se il processo si interrompe (es. un altro script chiude python.exe), si riavvia da solo.
:loop
python finanza_server.py
echo Server fermato, riavvio in 2 secondi...
timeout /t 2 /nobreak >nul
goto loop

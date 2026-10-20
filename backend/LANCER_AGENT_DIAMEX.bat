@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo DiameX Local Agent
Echo ========================================
echo.

echo Lancement de l'agent local...
echo Les scans TIFF seront convertis en PDF pour l'ouverture locale et l'upload web.
python diamex_local_agent.py

echo.
echo Agent arrete.
pause

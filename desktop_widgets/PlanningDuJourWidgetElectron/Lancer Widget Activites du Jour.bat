@echo off
cd /d "%~dp0"
set "ELECTRON_EXE=%~dp0..\WeatherWidgetElectron\node_modules\electron\dist\electron.exe"
if not exist "%ELECTRON_EXE%" (
  echo Electron introuvable dans WeatherWidgetElectron.
  pause
  exit /b 1
)
start "" "%ELECTRON_EXE%" "%~dp0"

@echo off
setlocal

set "APP_DIR=%~dp0"
set "PYTHON=C:\Python314\python.exe"
set "MT5=C:\Program Files\MetaTrader 5\terminal64.exe"
set "SCRIPT=%APP_DIR%pro_regime_structure.py"
set "DASHBOARD_URL=http://127.0.0.1:8765/"

if not exist "%PYTHON%" (
    echo Python tidak ditemukan: %PYTHON%
    pause
    exit /b 1
)

if not exist "%MT5%" (
    echo MetaTrader 5 tidak ditemukan: %MT5%
    pause
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo File aplikasi tidak ditemukan: %SCRIPT%
    pause
    exit /b 1
)

start "Atlas MT5 Monitor" /min "%PYTHON%" "%SCRIPT%" --symbol XAUUSD.m --timeframe M5 --higher-timeframe M15 --mode scalping --terminal "%MT5%" --web --allow-auto-pilot --auto-risk-percent 0.25 --daily-loss-limit-percent 1.0 --poll-seconds 0.5

powershell.exe -NoProfile -Command "$ready=$false; for($i=0; $i -lt 60; $i++){try{$status=Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/status' -TimeoutSec 1; if($status.auto_pilot_available -and $status.auto_risk_percent -eq 0.25 -and $status.daily_loss_limit_percent -eq 1.0 -and $status.higher_timeframe -eq 'M15' -and $status.symbols.Count -gt 0){$ready=$true; break}}catch{}; Start-Sleep -Milliseconds 500}; if($ready){exit 0}else{exit 1}"
if errorlevel 1 (
    echo Dashboard tidak merespons. Pastikan MT5 sudah login dan periksa jendela Atlas yang diminimalkan.
    pause
    exit /b 1
)

start "" "%DASHBOARD_URL%"
exit /b 0

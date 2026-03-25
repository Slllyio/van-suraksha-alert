@echo off
REM ============================================================
REM Van Suraksha Daily Fire Alert - Windows Scheduled Task
REM ============================================================
REM Runs daily at 06:00 AM IST:
REM   1. Updates FWI from NASA POWER
REM   2. Fetches NRT FIRMS detections
REM   3. Generates detection alerts
REM   4. Runs PREDICTIVE model for tomorrow's risk map
REM   5. Builds unified GeoJSON feed for dashboard
REM
REM Run this script as Administrator to register the task.
REM ============================================================

set PYTHON=C:\Users\S.C.C\AppData\Local\Programs\Python\Python312\python.exe
set SCRIPT=E:\FIRE\scripts\daily_fire_alert.py
set TASK_NAME=VanSuraksha_DailyAlert

echo.
echo Van Suraksha Alert System - Task Registration
echo ==============================================

REM Register the daily task at 06:00 AM
schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHON%\" \"%SCRIPT%\"" /sc daily /st 06:00 /f /rl highest

if %errorlevel% equ 0 (
    echo.
    echo SUCCESS: Task "%TASK_NAME%" registered.
    echo.
    echo   Schedule:    Daily at 06:00 AM
    echo   Script:      %SCRIPT%
    echo   Logs:        E:\FIRE\logs\
    echo   Feed output: E:\FIRE\outputs\dashboard_feed\
    echo.
    echo Pipeline steps:
    echo   1. Update FWI indices from NASA POWER
    echo   2. Fetch FIRMS NRT fire detections
    echo   3. Generate detection-based alerts
    echo   4. Run predictive model ^(tomorrow's risk map^)
    echo   5. Build unified alert feed ^(detection + prediction^)
    echo.
    echo Commands:
    echo   Run now:     schtasks /run /tn "%TASK_NAME%"
    echo   Check:       schtasks /query /tn "%TASK_NAME%" /v
    echo   Delete:      schtasks /delete /tn "%TASK_NAME%" /f
    echo   Manual run:  python scripts/daily_fire_alert.py
    echo   Quick run:   python scripts/daily_fire_alert.py --skip-prediction
) else (
    echo.
    echo FAILED to register task. Try running as Administrator.
)
echo.
pause

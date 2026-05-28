@echo off
REM PowerPrice Signal Daemon — Windows Uninstaller
REM Removes both the NSSM service and the Task Scheduler task if present.
REM Run as Administrator.

setlocal

set SERVICE_NAME=PowerPriceSignalDaemon
set TASK_NAME=PowerPriceSignalDaemon
set NSSM=nssm

echo === PowerPrice Signal Daemon — Windows Uninstall ===

REM Stop and remove NSSM service if present
where %NSSM% >nul 2>&1
if not errorlevel 1 (
    %NSSM% status %SERVICE_NAME% >nul 2>&1
    if not errorlevel 1 (
        echo Stopping NSSM service...
        %NSSM% stop %SERVICE_NAME% confirm
        echo Removing NSSM service...
        %NSSM% remove %SERVICE_NAME% confirm
    ) else (
        echo NSSM service not found — skipping.
    )
) else (
    echo nssm.exe not in PATH — skipping service removal.
)

REM Remove Task Scheduler task if present
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo Removing Task Scheduler task...
    schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo Task Scheduler task not found — skipping.
)

echo.
echo Done. Daemon stopped and service/task removed.
echo Data files in .\data\ are preserved.

pause

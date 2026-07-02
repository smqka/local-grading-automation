@echo off
setlocal

cd /d "%~dp0.."

if not exist logs mkdir logs

echo [%date% %time%] Starting grading API>> logs\grading-api.log
if not "%PYTHON_EXE%"=="" (
  "%PYTHON_EXE%" -u -m grading_api.server >> logs\grading-api.log 2>>&1
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -u -m grading_api.server >> logs\grading-api.log 2>>&1
  ) else (
    python -u -m grading_api.server >> logs\grading-api.log 2>>&1
  )
)

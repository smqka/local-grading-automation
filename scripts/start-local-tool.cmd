@echo off
setlocal

set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

netstat -ano -p tcp | findstr /R /C:":8765 .*LISTENING" >nul
if errorlevel 1 (
  start "grading-api" /min "%ROOT%\scripts\run-grading-api.cmd"
) else (
  echo API is already running on 127.0.0.1:8765
)

netstat -ano -p tcp | findstr /R /C:":5175 .*LISTENING" >nul
if errorlevel 1 (
  start "grading-web" /min "%ROOT%\scripts\run-web.cmd"
) else (
  echo Web is already running on 127.0.0.1:5175
)

echo Exam grading assistant is starting.
echo Web: http://127.0.0.1:5175
echo API: http://127.0.0.1:8765
echo Logs: %ROOT%\logs

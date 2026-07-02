@echo off
setlocal

cd /d "%~dp0.."

if not exist logs mkdir logs
if "%PORT%"=="" set "PORT=5175"

echo [%date% %time%] Starting web server on port %PORT%>> logs\web.log
npm.cmd run dev >> logs\web.log 2>>&1

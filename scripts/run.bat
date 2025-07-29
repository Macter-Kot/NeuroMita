
@echo off
cd /d "%~dp0"
libs\python\python.exe -m uv run NeuroMita.pyz
pause

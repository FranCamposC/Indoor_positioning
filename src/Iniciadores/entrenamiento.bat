@echo off
cd /d "%~dp0"

start cmd /k ".venv\Scripts\python.exe xgboostmodel.py"


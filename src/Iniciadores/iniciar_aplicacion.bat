@echo off
cd /d "%~dp0"

start cmd /k ".venv\Scripts\python.exe prediccion.py"
start cmd /k ".venv\Scripts\python.exe accion.py"
start cmd /k ".venv\Scripts\python.exe -m streamlit run GUI.py"

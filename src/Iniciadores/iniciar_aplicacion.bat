@echo off
REM Movernos a la raíz del proyecto
pushd "%~dp0\..\.."

REM Comprobar que el entorno existe
if not exist ".venv\Scripts\python.exe" (
    echo El entorno virtual .venv no existe. Ejecuta primero setup_env.bat
    pause
    exit /b
)

REM Ejecutar los scripts en nuevas terminales
start cmd /k ".venv\Scripts\python.exe src\prediccion.py"
start cmd /k ".venv\Scripts\python.exe src\accion.py"
start cmd /k ".venv\Scripts\python.exe -m streamlit run src\GUI.py"

REM Volver al directorio original
popd

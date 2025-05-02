@echo off
REM Movernos a la raíz del proyecto
pushd "%~dp0\..\.."

REM Comprobamos que el entorno virtual existe
if not exist ".venv\Scripts\python.exe" (
    echo El entorno virtual no existe. Ejecuta primero setup_env.bat
    pause
    exit /b
)

REM Ejecutar xgboostmodel.py con el entorno virtual
start cmd /k ".venv\Scripts\python.exe src\xgboostmodel.py"

REM Volver al directorio original
popd

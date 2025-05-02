@echo off
REM Movernos a la raíz del proyecto de forma segura
pushd "%~dp0\..\.."

REM Comprobamos que el entorno existe
if not exist ".venv\Scripts\python.exe" (
    echo El entorno virtual no existe. Ejecútalo primero con setup_env.bat
    pause
    exit /b
)

REM Ejecutar save2.0.py con el Python del entorno virtual
start cmd /k ".venv\Scripts\python.exe src\save2.0.py"

REM Volver a donde estábamos
popd

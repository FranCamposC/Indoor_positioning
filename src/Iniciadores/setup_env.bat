@echo off
cd ..\..  && echo Cambiando al directorio raíz del proyecto...

echo Creando entorno virtual en .venv...
python -m venv .venv

echo Activando entorno virtual...
call .venv\Scripts\activate

echo Instalando dependencias desde src\Iniciadores\requirements.txt...
pip install --upgrade pip
pip install -r src\requirements.txt

echo Entorno configurado correctamente.
pause

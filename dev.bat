@echo off
rem Lanza myRef en modo desarrollo. Crea el entorno virtual la primera vez.
rem El proyecto requiere Python >=3.9 y <3.13 (ver pyproject.toml).
cd /d "%~dp0"

if exist .venv\Scripts\python.exe goto :run

set PYCMD=
for %%V in (3.12 3.11 3.10 3.9) do (
    if not defined PYCMD (
        py -%%V -c "" >nul 2>&1 && set PYCMD=py -%%V
    )
)
if not defined PYCMD (
    echo No se encontro Python 3.9 - 3.12. El proyecto no es compatible con 3.13 o superior.
    echo Instala Python 3.12 desde https://www.python.org/downloads/
    goto :error
)

echo Creando entorno virtual con %PYCMD%...
%PYCMD% -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e . || goto :error
pip install -r requirements\dev.txt || goto :error
goto :start

:run
call .venv\Scripts\activate.bat

:start
rem Recarga automatica: al guardar un archivo de myRef\ la app se reinicia
rem conservando el lienzo. Usa "python -m myRef" para arrancar sin recarga.
python -m myRef.devreload %*
exit /b %errorlevel%

:error
echo Error preparando el entorno.
pause
exit /b 1

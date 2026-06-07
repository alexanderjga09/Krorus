@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

title Krorus GUI

echo ============================================
echo   Krorus - Lanzador
echo ============================================
echo.

:: 1. Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    pause
    exit /b 1
)
echo [OK] Python detectado

:: 2. Verificar / crear entorno virtual aislado para la GUI
if not exist ".venv_gui\Scripts\python.exe" (
    echo.
    echo Creando entorno virtual para la GUI ^(.venv_gui^)...
    python -m venv .venv_gui
    if errorlevel 1 (
        echo [ERROR] No se pudo crear .venv_gui
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado.
)

:: 3. Verificar que Flet esta instalado en el venv
.venv_gui\Scripts\python -c "import flet" >nul 2>&1
if errorlevel 1 (
    echo Instalando Flet en .venv_gui...
    .venv_gui\Scripts\python -m pip install --quiet flet
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar Flet.
        pause
        exit /b 1
    )
    echo [OK] Flet instalado.
) else (
    echo [OK] Flet disponible.
)

:: 4. Lanzar la GUI y salir
echo.
echo Iniciando la aplicacion...
start "" ".venv_gui\Scripts\pythonw.exe" "setup_gui.py"
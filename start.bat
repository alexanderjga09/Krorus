@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Configurando e iniciando la aplicacion...
echo ============================================

:: 1. Verificar que Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no se encuentra en el PATH.
    echo Por favor, instala Python desde https://www.python.org/ y asegurate de marcarlo en el PATH.
    pause
    exit /b 1
)

:: 2. Verificar si pip está disponible
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip no esta disponible. Reinstala Python con la opcion de pip habilitada.
    pause
    exit /b 1
)

:: 3. Instalar ttkbootstrap si no está presente
echo Verificando dependencia: ttkbootstrap...
python -c "import ttkbootstrap" >nul 2>&1
if errorlevel 1 (
    echo Instalando ttkbootstrap...
    python -m pip install --quiet ttkbootstrap
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar ttkbootstrap. Revisa tu conexion a internet.
        pause
        exit /b 1
    )
    echo ttkbootstrap instalado correctamente.
) else (
    echo ttkbootstrap ya esta instalado.
)

:: 4. Ejecutar la GUI con pythonw (sin consola)
echo Iniciando la aplicacion...
start "" pythonw.exe "%~dp0setup_gui.py"

:: Si quieres mantener la consola abierta para ver mensajes, comenta la linea anterior y descomenta:
:: python "%~dp0setup_gui.py"
:: pause

exit /b 0

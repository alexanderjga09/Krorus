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

:: 3. Instalar Flet si no está presente
echo Verificando dependencia: Flet...
python -c "import flet" >nul 2>&1
if errorlevel 1 (
    echo Instalando Flet...
    python -m pip install --quiet flet
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar Flet. Revisa tu conexion a internet.
        pause
        exit /b 1
    )
    echo Flet instalado correctamente.
) else (
    echo Flet ya esta instalado.
)

:: 4. Ejecutar la GUI con pythonw (sin consola)
if exist "%~dp0setup_gui.py" (
    echo Iniciando la aplicacion...
    start "" pythonw.exe "%~dp0setup_gui.py"
) else (
    echo [ERROR] No se encontro el archivo "setup_gui.py" en el directorio actual.
    pause
    exit /b 1
)

:: Si quieres mantener la consola abierta para ver mensajes de error de Python, comenta las lineas anteriores y usa:
:: python "%~dp0setup_gui.py"
:: pause

exit /b 0

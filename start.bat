@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Configurando e iniciando la aplicacion...
echo ============================================

:: 1. Verificar que Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no se encuentra en el PATH.
    echo Por favor, instala Python desde https://www.python.org/ y asegurate de marcarlo en el PATH.
    pause
    exit /b 1
)

:: 2. Verificar si pip esta disponible
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip no esta disponible. Reinstala Python con la opcion de pip habilitada.
    pause
    exit /b 1
)

:: 3. Verificar que Git esta instalado (necesario para actualizaciones)
git --version >nul 2>&1
if errorlevel 1 (
    echo [ADVERTENCIA] Git no esta instalado o no se encuentra en el PATH.
    echo La funcion de actualizacion automatica no estara disponible.
    echo Puedes descargarlo desde https://git-scm.com/
    echo.
)

:: 4. Instalar Flet si no esta presente
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

:: 5. Ejecutar la GUI con pythonw (sin consola)
if exist "%~dp0setup_gui.py" (
    echo Iniciando la aplicacion...
    start "" pythonw.exe "%~dp0setup_gui.py"
) else (
    echo [ERROR] No se encontro el archivo "setup_gui.py" en el directorio actual.
    pause
    exit /b 1
)

exit /b 0
